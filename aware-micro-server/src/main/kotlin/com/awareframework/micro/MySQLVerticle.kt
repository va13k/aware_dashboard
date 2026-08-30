package com.awareframework.micro

import org.apache.commons.lang.StringEscapeUtils
import io.github.oshai.kotlinlogging.KotlinLogging
import io.vertx.config.ConfigRetriever
import io.vertx.config.ConfigRetrieverOptions
import io.vertx.config.ConfigStoreOptions
import io.vertx.core.AbstractVerticle
import io.vertx.core.Future
import io.vertx.core.Promise
import io.vertx.core.json.Json
import io.vertx.core.json.JsonArray
import io.vertx.core.json.JsonObject
import io.vertx.core.net.PemKeyCertOptions
import io.vertx.core.net.PemTrustOptions
import io.vertx.mysqlclient.MySQLConnectOptions
import io.vertx.mysqlclient.MySQLPool
import io.vertx.mysqlclient.SslMode
import io.vertx.sqlclient.PoolOptions
import io.vertx.sqlclient.SqlClient
import io.vertx.sqlclient.Tuple
import java.util.concurrent.ConcurrentHashMap
import java.util.stream.Collectors
import java.util.stream.StreamSupport

class MySQLVerticle : AbstractVerticle() {

  private val logger = KotlinLogging.logger {}

  private lateinit var parameters: JsonObject
  private lateinit var sqlClient: MySQLPool

  /** Whether a write is checked against the enrolment registry before it is stored. */
  private var requireEnrolment = false

  /**
   * Devices whose enrolment window has been read once.
   *
   * Positive answers only, so the set holds one entry per participating device and
   * a device that enrols later is admitted as soon as it writes again. A device
   * with no window is read from the registry on every batch, which is one indexed
   * lookup against a table holding a few rows per device.
   */
  private val enrolledDevices: MutableSet<String> = ConcurrentHashMap.newKeySet()

  /** Each table's columns, so a batch is shaped like the table it is going into. */
  private val tableColumns: MutableMap<String, Set<String>> = ConcurrentHashMap()

  override fun start(startPromise: Promise<Void>?) {
    super.start(startPromise)

    val configStore = ConfigStoreOptions()
      .setType("file")
      .setFormat("json")
      .setConfig(JsonObject().put("path", "aware-config.json"))

    val configRetrieverOptions = ConfigRetrieverOptions()
      .addStore(configStore)
      .setScanPeriod(5000)

    val eventBus = vertx.eventBus()

    val configReader = ConfigRetriever.create(vertx, configRetrieverOptions)
    configReader.getConfig { config ->
      if (config.succeeded() && config.result().containsKey("server")) {
        parameters = config.result()
        val serverConfig = parameters.getJsonObject("server")

        // https://vertx.io/docs/4.3.3/apidocs/io/vertx/mysqlclient/MySQLConnectOptions.html
        val connectOptions = MySQLConnectOptions()
          .setHost(serverConfig.getString("database_host"))
          .setPort(serverConfig.getInteger("database_port"))
          .setDatabase(serverConfig.getString("database_name"))
          .setUser(serverConfig.getString("database_user"))
          .setPassword(serverConfig.getString("database_pwd"))
        setDatabaseSslMode(serverConfig, connectOptions)

        requireEnrolment = serverConfig.getBoolean("require_enrolment", false)
        logger.info {
          if (requireEnrolment) {
            "AWARE Micro: writes are checked against device_enrolment"
          } else {
            "AWARE Micro: writes are stored without an enrolment check"
          }
        }

        val poolOptions = PoolOptions().setMaxSize(5)

        // Create the client pool
        sqlClient = MySQLPool.pool(vertx, connectOptions, poolOptions)

        // The reply is what lets a client know whether its rows are on the server.
        // `stored` false is a batch the rule turned away, and a failed reply is a
        // batch the database could not take, so the two arrive at the caller as
        // different answers.
        eventBus.consumer<JsonObject>("insertData") { receivedMessage ->
          val postData = receivedMessage.body()
          insertData(
            device_id = postData.getString("device_id"),
            table = postData.getString("table"),
            data = JsonArray(postData.getString("data"))
          )
            .onSuccess { stored ->
              if (stored) {
                recordContact(postData.getString("device_id"), postData.getString("table"))
              }
              receivedMessage.reply(JsonObject().put("stored", stored))
            }
            .onFailure { e -> receivedMessage.fail(500, e.message ?: "insert failed") }
        }

        eventBus.consumer<JsonObject>(Refusal.ADDRESS) { receivedMessage ->
          val refusal = receivedMessage.body()
          recordRefusal(
            device_id = refusal.getString("device_id") ?: "",
            table = refusal.getString("table") ?: "",
            reason = refusal.getString("reason") ?: "",
            rows = refusal.getInteger("rows") ?: 0
          )
        }

        eventBus.consumer<JsonObject>("updateData") { receivedMessage ->
          val postData = receivedMessage.body()
          updateData(
            device_id = postData.getString("device_id"),
            table = postData.getString("table"),
            data = JsonArray(postData.getString("data"))
          )
            .onSuccess { applied -> receivedMessage.reply(JsonObject().put("applied", applied)) }
            .onFailure { e -> receivedMessage.fail(500, e.message ?: "update failed") }
        }

        eventBus.consumer<JsonObject>("deleteData") { receivedMessage ->
          val postData = receivedMessage.body()
          deleteData(
            device_id = postData.getString("device_id"),
            table = postData.getString("table"),
            data = JsonArray(postData.getString("data"))
          )
            .onSuccess { removed -> receivedMessage.reply(JsonObject().put("removed", removed)) }
            .onFailure { e -> receivedMessage.fail(500, e.message ?: "delete failed") }
        }

        eventBus.consumer<JsonObject>("getData") { receivedMessage ->
          val postData = receivedMessage.body()
          getData(
            device_id = postData.getString("device_id"),
            table = postData.getString("table"),
            start = postData.getDouble("start"),
            end = postData.getDouble("end")
          )
            .onSuccess { rows -> receivedMessage.reply(rows) }
            // Answered as a failure, so a query this server refused reaches the
            // caller as a refusal rather than as an empty result it would read as
            // "this device has no rows in that period".
            .onFailure { e -> receivedMessage.fail(500, e.message ?: "query failed") }
        }
      }
    }
  }

  /**
   * Rows one device reported into one table over one period.
   *
   * The device and the period are bound rather than written into the statement:
   * they arrive as request parameters, so a quote in one of them would otherwise
   * end the literal it sits in and leave the rest of the segment to be read as
   * SQL --- and this route hands the rows it selects back to the caller, which
   * makes anything it can be made to select readable.
   *
   * The table is the part that cannot be bound. It is held to the shape of an
   * identifier and then asked of the schema, so a request naming something this
   * database does not have is refused before a statement exists.
   */
  fun getData(device_id: String, table: String, start: Double, end: Double): Future<JsonArray> {
    val quoted = TableName.quoted(table)
      ?: return Future.failedFuture(IllegalArgumentException("not a table name: $table"))

    val dataPromise: Promise<JsonArray> = Promise.promise()

    columnsOf(table).onFailure { e -> dataPromise.fail(e) }.onSuccess {
      sqlClient.getConnection { connectionResult ->
        if (connectionResult.succeeded()) {
          val connection = connectionResult.result()
          connection
            .preparedQuery(
              "SELECT * FROM $quoted WHERE device_id = ? " +
                "AND timestamp BETWEEN ? AND ? ORDER BY timestamp ASC"
            )
            .execute(Tuple.of(device_id, start, end))
            .onFailure { e ->
              logger.error(e) { "Failed to retrieve data." }
              connection.close()
              dataPromise.fail(e.message)
            }
            .onSuccess { rows ->
              logger.info { "$device_id : retrieved ${rows.size()} records from $table" }
              connection.close()
              dataPromise.complete(JsonArray(StreamSupport.stream(rows.spliterator(), false)
                .map { row -> row.toJson() }
                .collect(Collectors.toList())))
            }
        } else {
          logger.error(connectionResult.cause()) { "Failed to establish connection." }
          dataPromise.fail(connectionResult.cause())
        }
      }
    }

    return dataPromise.future()
  }

  /**
   * Rows a device asks to have rewritten, matched by the timestamps it names.
   *
   * Answered rather than assumed. The caller reads the result as "is what I sent
   * what the server now holds", so a batch the database did not take has to arrive
   * as a failure --- a client told the write happened stops offering it.
   *
   * Only a table storing a row whole has something to rewrite: the iOS schema keeps
   * a row's fields in a `data` column, and the Android schema gives each field a
   * column of its own with no `data` to put a row into. Asked of the schema, so the
   * two are told apart by what the table has rather than by which platform sent it.
   */
  fun updateData(device_id: String, table: String, data: JsonArray): Future<Boolean> {
    val quoted = TableName.quoted(table)
      ?: return Future.failedFuture(IllegalArgumentException("not a table name: $table"))
    if (data.isEmpty()) {
      logger.warn { "$device_id ignored empty update for $table" }
      return Future.succeededFuture(true)
    }

    val applied: Promise<Boolean> = Promise.promise()
    columnsOf(table).onFailure { e -> applied.fail(e) }.onSuccess { columns ->
      if (!columns.contains("data")) {
        logger.warn {
          "refused an update of $table from $device_id: the table stores each field " +
            "in a column of its own and holds no row to rewrite"
        }
        applied.complete(false)
      } else {
        val rows = (0 until data.size()).map { i ->
          val entry = data.getJsonObject(i)
          Tuple.of(entry.encode(), device_id, timestampFrom(entry))
        }
        sqlClient.getConnection { connectionResult ->
          if (connectionResult.succeeded()) {
            val connection = connectionResult.result()
            connection
              .preparedQuery(
                "UPDATE $quoted SET data = ? WHERE device_id = ? AND timestamp = ?"
              )
              .executeBatch(rows)
              .onFailure { e ->
                logger.error(e) { "Failed to process update." }
                connection.close()
                applied.fail(e)
              }
              .onSuccess { _ ->
                logger.info { "$device_id updated $table: ${rows.size} rows" }
                connection.close()
                applied.complete(true)
              }
          } else {
            logger.error(connectionResult.cause()) { "Failed to establish connection." }
            applied.fail(connectionResult.cause())
          }
        }
      }
    }
    return applied.future()
  }

  /**
   * Rows a device asks to have removed, by the timestamps it names.
   *
   * The one operation whose answer a study has to be able to trust: a participant
   * exercising the right to have their data taken out is told it happened by the
   * client, and the client is told by this. So the removal is answered when the
   * database has said what became of it, and a batch it could not take arrives at
   * the caller as a failure rather than as silence.
   */
  fun deleteData(device_id: String, table: String, data: JsonArray): Future<Boolean> {
    val quoted = TableName.quoted(table)
      ?: return Future.failedFuture(IllegalArgumentException("not a table name: $table"))

    val timestamps = (0 until data.size()).map { timestampFrom(data.getJsonObject(it)) }
    if (timestamps.isEmpty()) {
      logger.warn { "$device_id ignored empty delete for $table" }
      return Future.succeededFuture(true)
    }

    val removed: Promise<Boolean> = Promise.promise()
    columnsOf(table).onFailure { e -> removed.fail(e) }.onSuccess {
      val parameters = Tuple.of(device_id)
      timestamps.forEach { parameters.addDouble(it) }
      val placeholders = timestamps.joinToString(", ") { "?" }
      sqlClient.getConnection { connectionResult ->
        if (connectionResult.succeeded()) {
          val connection = connectionResult.result()
          connection
            .preparedQuery(
              "DELETE FROM $quoted WHERE device_id = ? AND timestamp IN ($placeholders)"
            )
            .execute(parameters)
            .onFailure { e ->
              logger.error(e) { "Failed to process delete batch." }
              connection.close()
              removed.fail(e)
            }
            .onSuccess { result ->
              logger.info {
                "$device_id deleted from $table: ${result.rowCount()} of " +
                  "${timestamps.size} rows named"
              }
              connection.close()
              removed.complete(true)
            }
        } else {
          logger.error(connectionResult.cause()) { "Failed to establish connection." }
          removed.fail(connectionResult.cause())
        }
      }
    }
    return removed.future()
  }

  /**
   * Insert batch of data into database table
   */
  private fun timestampFrom(entry: JsonObject): Double {
    return when (val timestamp = entry.getValue("timestamp")) {
      is Number -> timestamp.toDouble()
      is String -> timestamp.toDoubleOrNull() ?: System.currentTimeMillis().toDouble()
      else -> System.currentTimeMillis().toDouble()
    }
  }

  private fun sqlValue(value: String): String {
    return value.replace("\\", "\\\\").replace("'", "\\'")
  }

  private fun dataJsonFrom(value: Any?): JsonObject? {
    return when (value) {
      is JsonObject -> value
      is String -> try {
        JsonObject(value)
      } catch (_: Exception) {
        null
      }
      else -> null
    }
  }

  /** What the row on record says about the device, read in the shape it has. */
  private fun storedDeviceMetadata(
    row: io.vertx.sqlclient.Row,
    fields: List<String>,
    blobShaped: Boolean
  ): JsonObject {
    if (blobShaped) return dataJsonFrom(row.getValue("data")) ?: JsonObject()
    val stored = JsonObject()
    for (field in fields) {
      row.getValue(field)?.let { stored.put(field, it.toString()) }
    }
    return stored
  }

  private fun firstAwareDeviceEntry(
    device_id: String,
    data: JsonArray,
    fields: List<String>
  ): JsonObject? {
    for (i in 0 until data.size()) {
      val entry = data.getJsonObject(i)
      if (DeviceMetadata.isComplete(entry, fields)) {
        return entry
      }
      logger.warn {
        "$device_id ignored incomplete aware_device row with fields ${entry.fieldNames().sorted()}"
      }
      // A placeholder so the device is registered, carrying only what the phone
      // itself reported. The hardware fields stay absent until real metadata
      // arrives: the dashboard shows them beside genuinely reported values with
      // nothing to tell the two apart, so anything guessed here would reach a
      // researcher as the phone's own answer. The update above fills them in.
      return entry.copy()
        .put("device_id", device_id)
        .put("timestamp", timestampFrom(entry))
        .put("metadata_status", "pending")
        .put("metadata_complete", false)
    }
    return null
  }

  private fun rowId(row: io.vertx.sqlclient.Row): String? {
    return row.getValue("_id")?.toString()
  }

  private fun escapedJson(entry: JsonObject): String {
    return StringEscapeUtils.escapeJavaScript(entry.encode())
  }

  /**
   * Keep one row per device, and write only when what it says changes.
   *
   * The phone reports its make, model and label on every sync. Appending each
   * report would grow a row a minute per device, every one carrying the same
   * answer under a moving timestamp, so a write happens when a field differs from
   * the record and is skipped otherwise. The timestamp then marks when the
   * metadata last changed rather than when it was last repeated.
   */
  private fun insertAwareDeviceData(device_id: String, data: JsonArray): Future<Boolean> {
    return columnsOf("aware_device")
      .onFailure { e ->
        logger.error(e) { "Could not read the columns of aware_device; nothing was stored." }
      }
      .compose { columns -> storeDeviceMetadata(device_id, data, columns) }
  }

  private fun storeDeviceMetadata(
    device_id: String,
    data: JsonArray,
    columns: Set<String>
  ): Future<Boolean> {
    val blobShaped = columns.contains("data")
    val fields = DeviceMetadata.fieldsKeptBy(columns)
    val entry = firstAwareDeviceEntry(device_id, data, fields)
    if (entry == null) {
      logger.warn { "$device_id ignored empty aware_device insert" }
      return Future.succeededFuture(true)
    }
    val entryIsComplete = DeviceMetadata.isComplete(entry, fields)
    val written =
      if (blobShaped) listOf("device_id", "timestamp", "data")
      else columnsFor(JsonArray().add(entry), columns)
    val selected = (listOf("_id") + if (blobShaped) listOf("data") else fields)
      .joinToString(",") { "`$it`" }

    val stored: Promise<Boolean> = Promise.promise()
    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        connection
          .query("SELECT $selected FROM `aware_device` WHERE `device_id` = '${sqlValue(device_id)}'")
          .execute()
          .onFailure { e ->
            logger.error(e) { "Failed to check existing aware_device metadata." }
            connection.close()
            stored.fail(e)
          }
          .onSuccess { rows ->
            val existingRow = rows.toList().firstOrNull()
            val onRecord = existingRow?.let { storedDeviceMetadata(it, fields, blobShaped) }

            // Metadata the server already holds counts as stored: the row is
            // there, so the client has nothing left to deliver.
            if (onRecord != null && DeviceMetadata.isUnchanged(onRecord, entry, fields)) {
              logger.info { "$device_id ignored unchanged aware_device metadata" }
              connection.close()
              stored.complete(true)
              return@onSuccess
            }

            val existingRowId = existingRow?.let { rowId(it) }
            val query = if (existingRowId != null) {
              // A placeholder must not talk over an answer the phone already gave.
              if (!entryIsComplete && onRecord != null &&
                DeviceMetadata.isComplete(onRecord, fields)
              ) {
                logger.info { "$device_id ignored pending aware_device metadata" }
                connection.close()
                stored.complete(true)
                return@onSuccess
              }
              val assignments = written
                .filter { it != "device_id" }
                .joinToString(", ") { column -> "`$column` = ${deviceValue(entry, column)}" }
              "UPDATE `aware_device` SET $assignments WHERE `_id` = $existingRowId"
            } else {
              val columnList = written.joinToString(",") { "`$it`" }
              "INSERT INTO `aware_device` ($columnList) " +
                "VALUES ${rowValues(entry, device_id, written, blobShaped)}"
            }
            connection.query(query)
              .execute()
              .onFailure { e ->
                logger.error(e) { "Failed to insert aware_device metadata." }
                connection.close()
                stored.fail(e)
              }
              .onSuccess { _ ->
                logger.info { "$device_id saved to aware_device: 1 records" }
                connection.close()
                stored.complete(true)
              }
          }
      } else {
        logger.error(connectionResult.cause()) { "Failed to establish connection." }
        stored.fail(connectionResult.cause())
      }
    }
    return stored.future()
  }

  /** One column's value, rendered for a SET clause. */
  private fun deviceValue(entry: JsonObject, column: String): String {
    return when (column) {
      "timestamp" -> "'${timestampFrom(entry)}'"
      "data" -> "'${escapedJson(entry)}'"
      else -> {
        val value = entry.getValue(column)
        if (value == null) "NULL" else "'${sqlValue(value.toString())}'"
      }
    }
  }

  /**
   * Store a batch, and report what became of it.
   *
   * `true` is stored, `false` is turned away by the rule, and a failed future is a
   * database that could not take it. The caller answers its client from that, so a
   * batch the server does not hold is a batch the client still has.
   */
  fun insertData(table: String, device_id: String, data: JsonArray): Future<Boolean> {
    if (data.isEmpty()) {
      logger.warn { "$device_id ignored empty insert for $table" }
      return Future.succeededFuture(true)
    }

    // The last gate before the SQL, so the rule holds for every route that
    // publishes an insert rather than once per route. The data tables declare
    // `device_id varchar(150) DEFAULT ''`, so a blank id is accepted by MySQL and
    // lands as a row belonging to no device: counted by nothing, exportable by
    // nothing, and attributable only by its timestamps.
    if (device_id.isBlank()) {
      logger.warn { "refused an insert into $table with no device_id (${data.size()} rows)" }
      recordRefusal("", table, Refusal.NO_DEVICE_ID, data.size())
      return Future.succeededFuture(false)
    }

    if (!EnrolmentGate.mustConsultRegistry(requireEnrolment, table, device_id in enrolledDevices)) {
      return storeData(table, device_id, data)
    }

    // Recovery sits on the registry read alone, so a database that cannot take the
    // batch is reported as a failure rather than answered by reading the registry
    // again.
    return hasEnrolmentWindow(device_id)
      .map { enrolled ->
        if (enrolled) enrolledDevices.add(device_id)
        enrolled
      }
      .recover { e ->
        // Admitted, and the failure carried at error level. The registry says which
        // devices the study accounts for; unreachable, it says nothing about any of
        // them, and discarding a participant's collection because a lookup timed out
        // loses data the study cannot collect again. The answer stays unremembered,
        // so the next batch asks again.
        logger.error(e) {
          "stored an insert into $table from $device_id without reading device_enrolment " +
            "(${data.size()} rows)"
        }
        Future.succeededFuture(true)
      }
      .compose { admitted ->
        if (admitted) {
          storeData(table, device_id, data)
        } else {
          logger.warn {
            "refused an insert into $table from $device_id with no enrolment window " +
              "(${data.size()} rows)"
          }
          recordRefusal(device_id, table, Refusal.NO_ENROLMENT, data.size())
          Future.succeededFuture(false)
        }
      }
  }

  /**
   * Record a write that was turned away.
   *
   * One row per (device, reason), counting up rather than appending, so a phone
   * retrying every minute stays one line on screen with a rising count instead of
   * burying everything else. `first_seen` survives the upsert and `last_seen`
   * moves, which is what separates a single test insert from a week of retries.
   */
  private fun recordRefusal(device_id: String, table: String, reason: String, rows: Int) {
    val seenAt = System.currentTimeMillis()
    sqlClient
      .query(
        "INSERT INTO `refusals` " +
          "(`device_id`,`reason`,`attempts`,`rows_refused`,`last_table`,`first_seen`,`last_seen`) " +
          "VALUES ('${sqlValue(device_id)}', '${sqlValue(reason)}', 1, $rows, " +
          "'${sqlValue(table)}', $seenAt, $seenAt) " +
          "ON DUPLICATE KEY UPDATE `attempts` = `attempts` + 1, " +
          "`rows_refused` = `rows_refused` + $rows, " +
          "`last_table` = '${sqlValue(table)}', `last_seen` = $seenAt"
      )
      .execute()
      .onFailure { e ->
        logger.error(e) { "Failed to record a refused write from $device_id into $table." }
      }
  }

  /**
   * Record that the server accepted a batch from this device.
   *
   * This uses the server clock rather than a row timestamp supplied by the
   * phone. One upserted row per device is a connectivity signal, not research
   * data, and therefore remains separate from aware_device metadata and the
   * sensor tables.
   */
  private fun recordContact(device_id: String, table: String) {
    if (device_id.isBlank()) return

    val contactedAt = System.currentTimeMillis()
    sqlClient
      .query(
        "INSERT INTO `device_contacts` (`device_id`,`last_contact`,`last_table`) " +
          "VALUES ('${sqlValue(device_id)}', $contactedAt, '${sqlValue(table)}') " +
          "ON DUPLICATE KEY UPDATE `last_contact` = $contactedAt, " +
          "`last_table` = '${sqlValue(table)}'"
      )
      .execute()
      .onFailure { e ->
        logger.error(e) { "Failed to record a successful contact from $device_id for $table." }
      }
  }

  /**
   * Whether the registry holds a window this device earned by joining.
   *
   * One indexed read on the primary key's leading column, returning at the first
   * row so a device with several windows costs the same as a device with one.
   */
  private fun hasEnrolmentWindow(device_id: String): Future<Boolean> {
    val enrolmentPromise: Promise<Boolean> = Promise.promise()
    sqlClient
      .query(
        "SELECT 1 FROM `device_enrolment` WHERE `device_id` = '${sqlValue(device_id)}' " +
          "AND `join_source` IN (${EnrolmentGate.joinSourceList}) LIMIT 1"
      )
      .execute()
      .onFailure { e -> enrolmentPromise.fail(e) }
      .onSuccess { rows -> enrolmentPromise.complete(rows.size() > 0) }
    return enrolmentPromise.future()
  }

  /** Store a batch in the shape its table has, reporting whether the rows landed. */
  private fun storeData(table: String, device_id: String, data: JsonArray): Future<Boolean> {
    if (table == "aware_device") {
      return insertAwareDeviceData(device_id, data)
    }

    // The shape has to be the table's, not one shape for every table. The iOS
    // schema keeps a row's fields in a `data` column; the Android schema gives each
    // field its own column and has no `data` to put a blob in. One hardcoded column
    // list can serve one of them and silently fails the other.
    return columnsOf(table)
      .onFailure { e ->
        logger.error(e) { "Could not read the columns of $table; nothing was stored." }
      }
      .compose { columns -> writeBatch(table, device_id, data, columns) }
  }

  /**
   * The columns a table actually has, read once and remembered.
   *
   * Read from the schema rather than assumed, because the two platforms' tables
   * disagree about how a row is stored and the request does not say which it is
   * talking to. Cached because it changes only when somebody alters the table, and
   * a lookup per batch would be a round trip for an answer that does not move.
   */
  private fun columnsOf(table: String): Future<Set<String>> {
    tableColumns[table]?.let { return Future.succeededFuture(it) }

    val promise: Promise<Set<String>> = Promise.promise()
    sqlClient
      .query(
        "SELECT `COLUMN_NAME` FROM `information_schema`.`COLUMNS` " +
          "WHERE `TABLE_SCHEMA` = DATABASE() AND `TABLE_NAME` = '${sqlValue(table)}'"
      )
      .execute()
      .onFailure { e -> promise.fail(e) }
      .onSuccess { rows ->
        val found = rows.map { it.getString("COLUMN_NAME") }.toSet()
        if (found.isEmpty()) {
          promise.fail(IllegalStateException("table $table does not exist"))
        } else {
          tableColumns[table] = found
          promise.complete(found)
        }
      }
    return promise.future()
  }

  private fun writeBatch(
    table: String,
    device_id: String,
    data: JsonArray,
    columns: Set<String>
  ): Future<Boolean> {
    // The name is already one the schema answered for, and it is quoted into the
    // statement rather than bound, so it is held to the shape of an identifier here
    // as well: what reaches this is a request parameter either way.
    val quoted = TableName.quoted(table)
      ?: return Future.failedFuture(IllegalArgumentException("not a table name: $table"))

    // A `data` column means this table stores a row whole, which is the iOS shape
    // and the behaviour every existing deployment relies on. Anything else is
    // columnar, and each of the row's own fields goes to the column of that name.
    val blobShaped = columns.contains("data")
    val written: List<String> =
      if (blobShaped) listOf("device_id", "timestamp", "data")
      else columnsFor(data, columns)

    if (written.size <= 1) {
      logger.warn {
        "refused an insert into $table from $device_id: none of the row's fields " +
          "match its columns (${data.size()} rows)"
      }
      return Future.succeededFuture(false)
    }

    val stored: Promise<Boolean> = Promise.promise()
    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        val rows = data.size()
        val values = ArrayList<String>()
        for (i in 0 until data.size()) {
          val entry = data.getJsonObject(i)
          values.add(rowValues(entry, device_id, written, blobShaped))
        }
        val columnList = written.joinToString(",") { "`$it`" }
        val insertBatch =
          "INSERT INTO $quoted ($columnList) VALUES ${values.stream().map(Any::toString).collect(
            Collectors.joining(",")
          )}"
        connection.query(insertBatch)
          .execute()
          .onFailure { e ->
            logger.error(e) { "Failed to process batch." }
            connection.close()
            stored.fail(e)
          }
          .onSuccess { _ ->
            logger.info { "$device_id inserted to $table: $rows records" }
            connection.close()
            stored.complete(true)
          }
      } else {
        logger.error(connectionResult.cause()) { "Failed to establish connection." }
        stored.fail(connectionResult.cause())
      }
    }
    return stored.future()
  }

  /**
   * Which columns a columnar batch writes: `device_id` plus every field the rows
   * carry that the table has a column for.
   *
   * The union across the batch rather than the first row's keys, because a sensor
   * may omit a field it had nothing to report for, and taking the first row alone
   * would drop that column for the whole batch. Fields the table does not have are
   * left out rather than refused: a client newer than the schema should not lose
   * everything it sent for the sake of one column nobody added yet.
   */
  private fun columnsFor(data: JsonArray, columns: Set<String>): List<String> {
    val present = LinkedHashSet<String>()
    present.add("device_id")
    for (i in 0 until data.size()) {
      for (field in data.getJsonObject(i).fieldNames()) {
        if (field != "device_id" && columns.contains(field)) present.add(field)
      }
    }
    return present.toList()
  }

  private fun rowValues(
    entry: JsonObject,
    device_id: String,
    written: List<String>,
    blobShaped: Boolean
  ): String {
    if (blobShaped) {
      // https://github.com/eclipse-vertx/vert.x/commit/ea0eddb129530ab3719c0ef86b471894876ec519#diff-07f061e092a63da24a06ab4507d15125e3377034f21eee18c6d4261f6714e709L241
      return "('${sqlValue(device_id)}', '${timestampFrom(entry)}', '${escapedJson(entry)}')"
    }
    val rendered = written.map { column ->
      when (column) {
        "device_id" -> "'${sqlValue(device_id)}'"
        "timestamp" -> "'${timestampFrom(entry)}'"
        else -> {
          val value = entry.getValue(column)
          // NULL rather than the empty string: a field the row did not carry is
          // absent, and a column's own default is a better answer than a value
          // invented here.
          if (value == null) "NULL" else "'${sqlValue(value.toString())}'"
        }
      }
    }
    return "(${rendered.joinToString(", ")})"
  }

  override fun stop() {
    super.stop()
    logger.info { "AWARE Micro: MySQL client shutdown" }
    sqlClient.close()
  }

  /**
   * The client's TLS setting for the database connection.
   *
   * Every encrypting mode reaches a completed handshake by way of trust material.
   * `database_ssl_path_ca_cert_pem` names a CA to check the server against; where
   * the configuration leaves it out, the client takes the server's certificate as
   * presented, so the traffic is encrypted and the server is the one the network
   * route leads to. That is this deployment's own shape: the database answers on a
   * private network under a certificate it generated for itself.
   *
   * `verify-ca` and `verify-identity` are the modes whose subject is that identity,
   * so each asks for the CA. `verify-identity` also matches the certificate against
   * the host it was reached at, which asks that certificate to carry the host as a
   * subject alternative name.
   *
   * A mode outside this set is logged and read as `preferred`, which encrypts
   * against a server offering TLS and connects to one serving plaintext.
   */
  private fun setDatabaseSslMode(serverConfig: JsonObject, options: MySQLConnectOptions) {
    when (val sslMode = serverConfig.getString("database_ssl_mode")?.trim()?.lowercase()) {
      null, "", "disable", "disabled" -> {
        options.setSslMode(SslMode.DISABLED)
        logger.info { "AWARE Micro: MySQL connection is plaintext" }
      }
      "prefer", "preferred" -> encryptConnection(serverConfig, options, SslMode.PREFERRED)
      "require", "required" -> encryptConnection(serverConfig, options, SslMode.REQUIRED)
      "verify-ca", "verify_ca" -> verifyServer(serverConfig, options, SslMode.VERIFY_CA)
      "verify-identity", "verify_identity" ->
        verifyServer(serverConfig, options, SslMode.VERIFY_IDENTITY)
      else -> {
        logger.warn {
          "AWARE Micro: database_ssl_mode '$sslMode' reads as 'preferred'. " +
            "The modes are disabled, preferred, required, verify-ca and verify-identity"
        }
        encryptConnection(serverConfig, options, SslMode.PREFERRED)
      }
    }
  }

  /** Encrypts the connection, against the configured CA or the server as presented. */
  private fun encryptConnection(
    serverConfig: JsonObject,
    options: MySQLConnectOptions,
    mode: SslMode
  ) {
    options.setSslMode(mode)
    val caCertPath = serverConfig.getString("database_ssl_path_ca_cert_pem")
    if (caCertPath.isNullOrBlank()) {
      options.setTrustAll(true)
      logger.info { "AWARE Micro: MySQL connection is '$mode', trusting the server as presented" }
    } else {
      trustCaCert(serverConfig, options, caCertPath)
      logger.info { "AWARE Micro: MySQL connection is '$mode', trusting $caCertPath" }
    }
  }

  /** Encrypts the connection and checks the server's certificate against the configured CA. */
  private fun verifyServer(
    serverConfig: JsonObject,
    options: MySQLConnectOptions,
    mode: SslMode
  ) {
    val caCertPath = serverConfig.getString("database_ssl_path_ca_cert_pem")
    if (caCertPath.isNullOrBlank()) {
      logger.warn {
        "AWARE Micro: database_ssl_mode '$mode' reads as 'required'. " +
          "Checking the server's certificate asks for database_ssl_path_ca_cert_pem"
      }
      encryptConnection(serverConfig, options, SslMode.REQUIRED)
      return
    }
    options.setSslMode(mode)
    trustCaCert(serverConfig, options, caCertPath)
    if (mode == SslMode.VERIFY_IDENTITY) {
      options.setHostnameVerificationAlgorithm("HTTPS")
    }
    logger.info { "AWARE Micro: MySQL connection is '$mode', trusting $caCertPath" }
  }

  /** Trusts the configured CA, and presents a client certificate where one is configured. */
  private fun trustCaCert(
    serverConfig: JsonObject,
    options: MySQLConnectOptions,
    caCertPath: String
  ) {
    options.setPemTrustOptions(PemTrustOptions().addCertPath(caCertPath))
    val clientKeyPath = serverConfig.getString("database_ssl_path_client_key_pem")
    val clientCertPath = serverConfig.getString("database_ssl_path_client_cert_pem")
    if (!clientKeyPath.isNullOrBlank() && !clientCertPath.isNullOrBlank()) {
      options.setPemKeyCertOptions(
        PemKeyCertOptions()
          .setKeyPath(clientKeyPath)
          .setCertPath(clientCertPath)
      )
    }
  }
}
