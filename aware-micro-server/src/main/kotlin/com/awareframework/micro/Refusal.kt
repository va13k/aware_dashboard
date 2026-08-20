package com.awareframework.micro

import io.vertx.core.json.JsonObject

/**
 * The vocabulary of a refused write, shared by whatever turns one away and the
 * verticle that records it.
 *
 * A refused write stores nothing, so the only trace it leaves is what is recorded
 * here. The route and the write sit in different verticles and only one of them
 * holds a database connection, so a refusal travels the event bus to be written.
 */
object Refusal {

  /** The event bus address a refusal is reported on. */
  const val ADDRESS = "recordRefusal"

  /** The device holds no enrolment window the study log put there. */
  const val NO_ENROLMENT = "no_enrolment"

  /** The request named no device at all. */
  const val NO_DEVICE_ID = "no_device_id"

  /**
   * A refusal as it travels the event bus.
   *
   * `rows` is how many rows the batch carried, counted separately from the
   * attempt: one request offering ten thousand rows and ten thousand offering one
   * are the same number of attempts and very different events.
   */
  fun message(deviceId: String, table: String, reason: String, rows: Int): JsonObject {
    return JsonObject()
      .put("device_id", deviceId)
      .put("table", table)
      .put("reason", reason)
      .put("rows", rows)
  }
}
