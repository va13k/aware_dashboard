package com.awareframework.micro

import org.apache.commons.lang.StringEscapeUtils
import io.github.oshai.kotlinlogging.KotlinLogging
import io.vertx.config.ConfigRetriever
import io.vertx.config.ConfigRetrieverOptions
import io.vertx.config.ConfigStoreOptions
import io.vertx.core.AbstractVerticle
import io.vertx.core.Future
import io.vertx.core.Promise
import io.vertx.core.json.JsonArray
import io.vertx.core.json.JsonObject
import io.vertx.core.net.PemKeyCertOptions
import io.vertx.core.net.PemTrustOptions
import io.vertx.pgclient.PgConnectOptions
import io.vertx.pgclient.PgPool
import io.vertx.pgclient.SslMode
import io.vertx.sqlclient.PoolOptions
import io.vertx.sqlclient.SqlClient
import io.vertx.sqlclient.Tuple
import java.util.concurrent.ConcurrentHashMap
import java.util.stream.Collectors
import java.util.stream.StreamSupport

class PostgresVerticle : AbstractVerticle() {

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
  private lateinit var sqlClient: PgPool

  /** Whether a write is checked against the enrolment registry before it is stored. */
  private var requireEnrolment = false

  /**
   * Devices whose enrolment window has been read once.
   *
   * Positive answers only, so the set holds one entry per participating device and
   * a device that enrols later is admitted as soon as it writes again.
   */
  private val enrolledDevices: MutableSet<String> = ConcurrentHashMap.newKeySet()

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

        // https://vertx.io/docs/4.3.3/apidocs/io/vertx/pgclient/PgConnectOptions.html
        val connectOptions = PgConnectOptions()
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
        sqlClient = PgPool.pool(vertx, connectOptions, poolOptions)

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
          .query("SELECT * FROM \"$table\" WHERE \"device_id\" = '$device_id' AND \"timestamp\" between $start AND $end ORDER BY \"timestamp\" ASC")
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

  /** Rows a device asks to have rewritten, answered once the database has acted. */
  fun updateData(device_id: String, table: String, data: JsonArray): Future<Boolean> {
    val quoted = TableName.quotedAnsi(table)
      ?: return Future.failedFuture(IllegalArgumentException("not a table name: $table"))
    if (data.isEmpty()) {
      logger.warn { "$device_id ignored empty update for $table" }
      return Future.succeededFuture(true)
    }

    val rows = (0 until data.size()).map { i ->
      val entry = data.getJsonObject(i)
      Tuple.of(entry.encode(), device_id, entry.getDouble("timestamp"))
    }

    val applied: Promise<Boolean> = Promise.promise()
    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        connection
          .preparedQuery(
            "UPDATE $quoted SET \"data\" = \$1 " +
              "WHERE \"device_id\" = \$2 AND \"timestamp\" = \$3"
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
    return applied.future()
  }

  /** Rows a device asks to have removed, answered once the database has acted. */
  fun deleteData(device_id: String, table: String, data: JsonArray): Future<Boolean> {
    val quoted = TableName.quotedAnsi(table)
      ?: return Future.failedFuture(IllegalArgumentException("not a table name: $table"))

    val timestamps = (0 until data.size()).map { data.getJsonObject(it).getDouble("timestamp") }
    if (timestamps.isEmpty()) {
      logger.warn { "$device_id ignored empty delete for $table" }
      return Future.succeededFuture(true)
    }

    val parameters = Tuple.of(device_id)
    timestamps.forEach { parameters.addDouble(it) }
    // Numbered from two, because the device holds the first place.
    val placeholders = timestamps.indices.joinToString(", ") { "\$${it + 2}" }

    val removed: Promise<Boolean> = Promise.promise()
    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connection = connectionResult.result()
        connection
          .preparedQuery(
            "DELETE FROM $quoted WHERE \"device_id\" = \$1 " +
              "AND \"timestamp\" IN ($placeholders)"
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
    return removed.future()
  }

  /**
   * Create a database table if it doesn't exist
   */
  fun createTable(table: String): Future<Boolean> {
    val promise = Promise.promise<Boolean>()
    sqlClient.getConnection { connectionResult ->
      if (connectionResult.succeeded()) {
        val connect = connectionResult.result()
        val queryCreateTable = "CREATE TABLE IF NOT EXISTS \"$table\" (\"_id\" SERIAL PRIMARY KEY, \"timestamp\" DOUBLE PRECISION NOT NULL, \"device_id\" UUID NOT NULL, \"data\" JSONB NOT NULL)"
        connect.query(queryCreateTable)
          .execute()
          .onFailure { e ->
            logger.error(e) { "Failed in: $queryCreateTable" }
            promise.fail(e.message)
            connect.close()
          }
          .onSuccess { _ ->
            logger.debug { "Created table \"$table\" successfully: $queryCreateTable" }
            val queryCreateIndex = "CREATE INDEX IF NOT EXISTS \"${table}_timestamp_device\" ON \"$table\" (\"timestamp\", \"device_id\")"
            connect.query(queryCreateIndex)
              .execute()
              .onFailure { e2 ->
                logger.error(e2) { "Failed in: $queryCreateIndex" }
                promise.fail(e2.message)
                connect.close()
              }
              .onSuccess { _ ->
                logger.debug { "Created index for \"$table\" successfully: $queryCreateIndex" }
                promise.complete(true)
                connect.close()
              }
          }
      } else {
        logger.error(connectionResult.cause()) { "Failed to connect to database for creating a table." }
        promise.fail(connectionResult.cause().message)
      }
    }
    return promise.future()
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
    return value.replace("'", "''")
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

  private fun insertAwareDeviceData(device_id: String, data: JsonArray) {
    val entry = firstAwareDeviceEntry(device_id, data)
    if (entry == null) {
      logger.warn { "$device_id ignored empty aware_device insert" }
      return
    }
    val entryIsComplete = isCompleteDeviceMetadata(entry)

    createTable("aware_device")
      .onSuccess { _ ->
        sqlClient.getConnection { connectionResult ->
          if (connectionResult.succeeded()) {
            val connection = connectionResult.result()
            connection
              .query("SELECT \"_id\", \"data\" FROM \"aware_device\" WHERE \"device_id\" = '${sqlValue(device_id)}'")
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
                  "UPDATE \"aware_device\" SET \"timestamp\" = '${timestampFrom(entry)}', \"data\" = '${sqlValue(entry.encode())}' WHERE \"_id\" = $existingRowId"
                } else {
                  "INSERT INTO \"aware_device\" (\"device_id\",\"timestamp\",\"data\") VALUES ('${sqlValue(device_id)}', '${timestampFrom(entry)}', '${sqlValue(entry.encode())}')"
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
      .onFailure { e ->
        logger.error(e) { "Failed to create aware_device table." }
      }
  }

  fun insertData(table: String, device_id: String, data: JsonArray) {
    if (data.isEmpty()) {
      return
    }

    // The same gate the MySQL path carries. Postgres declares the column NOT NULL
    // and would reject a null, but an empty string satisfies that and stores a row
    // belonging to no device just as readily.
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
        // Stored, and the failure carried at error level, on the same reading the
        // MySQL path takes: a registry that cannot be read says nothing about any
        // device, and a participant's collection is not recoverable once dropped.
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
   * retrying every minute stays one line on screen with a rising count.
   */
  private fun recordRefusal(device_id: String, table: String, reason: String, rows: Int) {
    val seenAt = System.currentTimeMillis()
    sqlClient
      .query(
        "INSERT INTO \"refusals\" " +
          "(\"device_id\",\"reason\",\"attempts\",\"rows_refused\",\"last_table\"," +
          "\"first_seen\",\"last_seen\") " +
          "VALUES ('${sqlValue(device_id)}', '${sqlValue(reason)}', 1, $rows, " +
          "'${sqlValue(table)}', $seenAt, $seenAt) " +
          "ON CONFLICT (\"device_id\", \"reason\") DO UPDATE SET " +
          "\"attempts\" = \"refusals\".\"attempts\" + 1, " +
          "\"rows_refused\" = \"refusals\".\"rows_refused\" + $rows, " +
          "\"last_table\" = '${sqlValue(table)}', \"last_seen\" = $seenAt"
      )
      .execute()
      .onFailure { e ->
        logger.error(e) { "Failed to record a refused write from $device_id into $table." }
      }
  }

  /**
   * Whether the registry holds a window this device earned by joining.
   */
  private fun hasEnrolmentWindow(device_id: String): Future<Boolean> {
    val enrolmentPromise: Promise<Boolean> = Promise.promise()
    sqlClient
      .query(
        "SELECT 1 FROM \"device_enrolment\" WHERE \"device_id\" = '${sqlValue(device_id)}' " +
          "AND \"join_source\" IN (${EnrolmentGate.joinSourceList}) LIMIT 1"
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

    createTable(table)
      .onSuccess { _ ->
        sqlClient.getConnection { connectionResult ->
          if (connectionResult.succeeded()) {
            val connection = connectionResult.result()
            val rows = data.size()
            val values = ArrayList<String>()
            for (i in 0 until data.size()) {
              val entry = data.getJsonObject(i)

              // https://github.com/eclipse-vertx/vert.x/commit/ea0eddb129530ab3719c0ef86b471894876ec519#diff-07f061e092a63da24a06ab4507d15125e3377034f21eee18c6d4261f6714e709L241
              values.add("('$device_id', '${timestampFrom(entry)}', '${entry.encode()}')")
            }
            val insertBatch =
              "INSERT INTO \"$table\" (\"device_id\",\"timestamp\",\"data\") VALUES ${values.stream().map(Any::toString).collect(
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
      .onFailure { e ->
        logger.error(e) { "Failed to create table." }
      }
  }

  override fun stop() {
    super.stop()
    logger.info { "AWARE Micro: PostgreSQL client shutdown" }
    sqlClient.close()
  }

  /**
   * The client's TLS setting for the database connection.
   *
   * Every encrypting mode reaches a completed handshake by way of trust material.
   * `database_ssl_path_ca_cert_pem` names a CA to check the server against; where
   * the configuration leaves it out, the client takes the server's certificate as
   * presented, so the traffic is encrypted and the server is the one the network
   * route leads to.
   *
   * `verify-ca` and `verify-full` are the modes whose subject is that identity, so
   * each asks for the CA. `verify-full` also matches the certificate against the
   * host it was reached at, which asks that certificate to carry the host as a
   * subject alternative name.
   *
   * A mode outside this set is logged and read as `prefer`, which encrypts against
   * a server offering TLS and connects to one serving plaintext.
   */
  private fun setDatabaseSslMode(serverConfig: JsonObject, options: PgConnectOptions) {
    when (val sslMode = serverConfig.getString("database_ssl_mode")?.trim()?.lowercase()) {
      null, "", "disable", "disabled" -> {
        options.setSslMode(SslMode.DISABLE)
        logger.info { "AWARE Micro: PostgreSQL connection is plaintext" }
      }
      "allow" -> encryptConnection(serverConfig, options, SslMode.ALLOW)
      "prefer", "preferred" -> encryptConnection(serverConfig, options, SslMode.PREFER)
      "require", "required" -> encryptConnection(serverConfig, options, SslMode.REQUIRE)
      "verify-ca", "verify_ca" -> verifyServer(serverConfig, options, SslMode.VERIFY_CA)
      "verify-full", "verify_full" -> verifyServer(serverConfig, options, SslMode.VERIFY_FULL)
      else -> {
        logger.warn {
          "AWARE Micro: database_ssl_mode '$sslMode' reads as 'prefer'. " +
            "The modes are disabled, allow, prefer, require, verify-ca and verify-full"
        }
        encryptConnection(serverConfig, options, SslMode.PREFER)
      }
    }
  }

  /** Encrypts the connection, against the configured CA or the server as presented. */
  private fun encryptConnection(
    serverConfig: JsonObject,
    options: PgConnectOptions,
    mode: SslMode
  ) {
    options.setSslMode(mode)
    val caCertPath = serverConfig.getString("database_ssl_path_ca_cert_pem")
    if (caCertPath.isNullOrBlank()) {
      options.setTrustAll(true)
      logger.info {
        "AWARE Micro: PostgreSQL connection is '$mode', trusting the server as presented"
      }
    } else {
      trustCaCert(serverConfig, options, caCertPath)
      logger.info { "AWARE Micro: PostgreSQL connection is '$mode', trusting $caCertPath" }
    }
  }

  /** Encrypts the connection and checks the server's certificate against the configured CA. */
  private fun verifyServer(
    serverConfig: JsonObject,
    options: PgConnectOptions,
    mode: SslMode
  ) {
    val caCertPath = serverConfig.getString("database_ssl_path_ca_cert_pem")
    if (caCertPath.isNullOrBlank()) {
      logger.warn {
        "AWARE Micro: database_ssl_mode '$mode' reads as 'require'. " +
          "Checking the server's certificate asks for database_ssl_path_ca_cert_pem"
      }
      encryptConnection(serverConfig, options, SslMode.REQUIRE)
      return
    }
    options.setSslMode(mode)
    trustCaCert(serverConfig, options, caCertPath)
    if (mode == SslMode.VERIFY_FULL) {
      options.setHostnameVerificationAlgorithm("HTTPS")
    }
    logger.info { "AWARE Micro: PostgreSQL connection is '$mode', trusting $caCertPath" }
  }

  /** Trusts the configured CA, and presents a client certificate where one is configured. */
  private fun trustCaCert(
    serverConfig: JsonObject,
    options: PgConnectOptions,
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
