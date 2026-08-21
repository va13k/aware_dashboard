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
import java.util.concurrent.ConcurrentHashMap
import java.util.stream.Collectors
import java.util.stream.StreamSupport

class MySQLVerticle : AbstractVerticle() {

  private val logger = KotlinLogging.logger {}
  private val deviceMetadataFields = listOf(
    "board",
    "brand",
    "device",
    "build_id",
    "hardware",
    "manufacturer",
    "model",
    "product",
    "serial",
    "release",
    "release_type",
    "sdk",
    "label"
  )

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

        eventBus.consumer<JsonObject>("insertData") { receivedMessage ->
          val postData = receivedMessage.body()
          insertData(
            device_id = postData.getString("device_id"),
            table = postData.getString("table"),
            data = JsonArray(postData.getString("data"))
          )
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
        }

        eventBus.consumer<JsonObject>("deleteData") { receivedMessage ->
          val postData = receivedMessage.body()
          deleteData(
            device_id = postData.getString("device_id"),
            table = postData.getString("table"),
            data = JsonArray(postData.getString("data"))
          )
        }

        eventBus.consumer<JsonObject>("getData") { receivedMessage ->
          val postData = receivedMessage.body()
          getData(
            device_id = postData.getString("device_id"),
            table = postData.getString("table"),
            start = postData.getDouble("start"),
            end = postData.getDouble("end")
          // https://access.redhat.com/documentation/ja-jp/red_hat_build_of_eclipse_vert.x/4.0/html/eclipse_vert.x_4.0_migration_guide/changes-in-handlers_changes-in-common-components
          ).onComplete { response ->
            receivedMessage.reply(response.result())
          }
        }
      }
    }
  }

  //Fetch data from the database and return results as JsonArray
  fun getData(device_id: String, table: String, start: Double, end: Double): Future<JsonArray> {

    val dataPromise: Promise<JsonArray> = Promise.promise()

    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        // https://access.redhat.com/documentation/ja-jp/red_hat_build_of_eclipse_vert.x/4.0/html/eclipse_vert.x_4.0_migration_guide/changes-in-vertx-jdbc-client_changes-in-client-components#running_queries_on_managed_connections
        connection
          .query("SELECT * FROM $table WHERE device_id = '$device_id' AND timestamp between $start AND $end ORDER BY timestamp ASC")
          .execute()
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
      }
    }

    return dataPromise.future()
  }

  fun updateData(device_id: String, table: String, data: JsonArray) {
    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        for (i in 0 until data.size()) {
          val entry = data.getJsonObject(i)
          val updateItem =
            "UPDATE '$table' SET data = $entry WHERE device_id = '$device_id' AND timestamp = ${entry.getDouble("timestamp")}"

          // https://access.redhat.com/documentation/ja-jp/red_hat_build_of_eclipse_vert.x/4.0/html/eclipse_vert.x_4.0_migration_guide/changes-in-vertx-jdbc-client_changes-in-client-components#running_queries_on_managed_connections
          connection.query(updateItem)
            .execute()
            .onFailure { e ->
              logger.error(e) { "Failed to process update." }
              connection.close()
            }
            .onSuccess { _ ->
              logger.info { "$device_id updated $table: ${entry.encode()}" }
              connection.close()
            }
        }
      } else {
        logger.error(connectionResult.cause()) { "Failed to establish connection." }
      }
    }
  }

  fun deleteData(device_id: String, table: String, data: JsonArray) {
    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        val timestamps = mutableListOf<Double>()
        for (i in 0 until data.size()) {
          val entry = data.getJsonObject(i)
          timestamps.add(entry.getDouble("timestamp"))
        }

        val deleteBatch =
          "DELETE from '$table' WHERE device_id = '$device_id' AND timestamp in (${timestamps.stream().map(Any::toString).collect(
            Collectors.joining(",")
          )})"
        connection.query(deleteBatch)
          .execute()
          .onFailure { e ->
            logger.error(e) { "Failed to process delete batch." }
            connection.close()
          }
          .onSuccess { _ ->
            logger.info { "$device_id deleted from $table: ${data.size()} records" }
            connection.close()
          }
      } else {
        logger.error(connectionResult.cause()) { "Failed to establish connection." }
      }
    }
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

  private fun isCompleteDeviceMetadata(entry: JsonObject): Boolean {
    return deviceMetadataFields.all { field ->
      val value = entry.getValue(field)
      value != null && value.toString().isNotBlank()
    }
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

  private fun hasCompleteAwareDeviceRow(rows: Iterable<io.vertx.sqlclient.Row>): Boolean {
    return rows.any { row ->
      val data = dataJsonFrom(row.getValue("data"))
      data != null && isCompleteDeviceMetadata(data)
    }
  }

  private fun firstAwareDeviceEntry(device_id: String, data: JsonArray): JsonObject? {
    for (i in 0 until data.size()) {
      val entry = data.getJsonObject(i)
      if (isCompleteDeviceMetadata(entry)) {
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

  private fun insertAwareDeviceData(device_id: String, data: JsonArray) {
    val entry = firstAwareDeviceEntry(device_id, data)
    if (entry == null) {
      logger.warn { "$device_id ignored empty aware_device insert" }
      return
    }
    val entryIsComplete = isCompleteDeviceMetadata(entry)

    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        connection
          .query("SELECT `_id`, `data` FROM `aware_device` WHERE `device_id` = '${sqlValue(device_id)}'")
          .execute()
          .onFailure { e ->
            logger.error(e) { "Failed to check existing aware_device metadata." }
            connection.close()
          }
          .onSuccess { rows ->
            val existingRows = rows.toList()
            if (hasCompleteAwareDeviceRow(rows)) {
              logger.info { "$device_id ignored duplicate complete aware_device metadata" }
              connection.close()
              return@onSuccess
            }

            val existingRowId = existingRows.firstOrNull()?.let { rowId(it) }
            val query = if (existingRowId != null) {
              if (!entryIsComplete) {
                logger.info { "$device_id ignored duplicate pending aware_device metadata" }
                connection.close()
                return@onSuccess
              }
              "UPDATE `aware_device` SET `timestamp` = '${timestampFrom(entry)}', `data` = '${escapedJson(entry)}' WHERE `_id` = $existingRowId"
            } else {
              "INSERT INTO `aware_device` (`device_id`,`timestamp`,`data`) VALUES ('${sqlValue(device_id)}', '${timestampFrom(entry)}', '${escapedJson(entry)}')"
            }
            connection.query(query)
              .execute()
              .onFailure { e ->
                logger.error(e) { "Failed to insert aware_device metadata." }
                connection.close()
              }
              .onSuccess { _ ->
                logger.info { "$device_id saved to aware_device: 1 records" }
                connection.close()
              }
          }
      } else {
        logger.error(connectionResult.cause()) { "Failed to establish connection." }
      }
    }
  }

  fun insertData(table: String, device_id: String, data: JsonArray) {
    if (data.isEmpty()) {
      logger.warn { "$device_id ignored empty insert for $table" }
      return
    }

    // The last gate before the SQL, so the rule holds for every route that
    // publishes an insert rather than once per route. The data tables declare
    // `device_id varchar(150) DEFAULT ''`, so a blank id is accepted by MySQL and
    // lands as a row belonging to no device: counted by nothing, exportable by
    // nothing, and attributable only by its timestamps.
    if (device_id.isBlank()) {
      logger.warn { "refused an insert into $table with no device_id (${data.size()} rows)" }
      recordRefusal("", table, Refusal.NO_DEVICE_ID, data.size())
      return
    }

    if (!EnrolmentGate.mustConsultRegistry(requireEnrolment, table, device_id in enrolledDevices)) {
      storeData(table, device_id, data)
      return
    }

    hasEnrolmentWindow(device_id)
      .onSuccess { enrolled ->
        if (enrolled) {
          enrolledDevices.add(device_id)
          storeData(table, device_id, data)
        } else {
          logger.warn {
            "refused an insert into $table from $device_id with no enrolment window " +
              "(${data.size()} rows)"
          }
          recordRefusal(device_id, table, Refusal.NO_ENROLMENT, data.size())
        }
      }
      .onFailure { e ->
        // Stored, and the failure carried at error level. The registry says which
        // devices the study accounts for; unreachable, it says nothing about any of
        // them, and discarding a participant's collection because a lookup timed out
        // loses data the study cannot collect again.
        logger.error(e) {
          "stored an insert into $table from $device_id without reading device_enrolment " +
            "(${data.size()} rows)"
        }
        storeData(table, device_id, data)
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

  private fun storeData(table: String, device_id: String, data: JsonArray) {
    if (table == "aware_device") {
      insertAwareDeviceData(device_id, data)
      return
    }

    // The shape has to be the table's, not one shape for every table. The iOS
    // schema keeps a row's fields in a `data` column; the Android schema gives each
    // field its own column and has no `data` to put a blob in. One hardcoded column
    // list can serve one of them and silently fails the other.
    columnsOf(table)
      .onFailure { e ->
        logger.error(e) { "Could not read the columns of $table; nothing was stored." }
      }
      .onSuccess { columns -> writeBatch(table, device_id, data, columns) }
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
  ) {
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
      return
    }

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
          "INSERT INTO `$table` ($columnList) VALUES ${values.stream().map(Any::toString).collect(
            Collectors.joining(",")
          )}"
        connection.query(insertBatch)
          .execute()
          .onFailure { e ->
            logger.error(e) { "Failed to process batch." }
            connection.close()
          }
          .onSuccess { _ ->
            logger.info { "$device_id inserted to $table: $rows records" }
            connection.close()
          }
      }
    }
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
      return "('$device_id', '${timestampFrom(entry)}', '${escapedJson(entry)}')"
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

  private fun setDatabaseSslMode(serverConfig: JsonObject, options: MySQLConnectOptions) {
    val sslMode = serverConfig.getString("database_ssl_mode")
    when (sslMode) {
      null, "", "disable", "disabled" -> {
        options.setSslMode(SslMode.DISABLED)
      }
      "prefer", "preferred" -> {
        options.setSslMode(SslMode.PREFERRED)
        if (serverConfig.containsKey("database_ssl_path_ca_cert_pem")) {
          options.setPemTrustOptions(PemTrustOptions().addCertPath(serverConfig.getString("database_ssl_path_ca_cert_pem")))
          if (serverConfig.containsKey("database_ssl_path_client_key_pem")) {
            options.setPemKeyCertOptions(PemKeyCertOptions()
                .setKeyPath(serverConfig.getString("database_ssl_path_client_key_pem"))
                .setCertPath(serverConfig.getString("database_ssl_path_client_cert_pem")))
          }
        }
      }
    }
  }
}
