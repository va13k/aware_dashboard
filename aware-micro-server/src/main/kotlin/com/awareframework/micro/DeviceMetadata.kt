package com.awareframework.micro

import io.vertx.core.json.JsonObject

/**
 * What a table keeps about a device, and whether a report of it is worth writing.
 *
 * The phone reports its make, model and label on every sync, so nearly every
 * report repeats the last one. These rules decide which fields a table can hold
 * and whether a report says anything the stored row does not; the verticle does
 * the reading and the writing.
 */
object DeviceMetadata {

  /** Everything a client may report about itself. */
  val fields = listOf(
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

  /**
   * The fields this table keeps.
   *
   * A `data` column stores the row whole, which is the iOS shape, so every field
   * the client sends is kept. A columnar table keeps the fields it has columns
   * for: demanding one it has no column for marks every row incomplete for the
   * life of the study, and the device never gets its make and model.
   */
  fun fieldsKeptBy(columns: Set<String>): List<String> {
    if (columns.contains("data")) return fields
    return fields.filter { columns.contains(it) }
  }

  /** Whether the entry answers every field the table keeps. */
  fun isComplete(entry: JsonObject, kept: List<String>): Boolean {
    return kept.all { field ->
      val value = entry.getValue(field)
      value != null && value.toString().isNotBlank()
    }
  }

  /**
   * Whether the row on record already says what this entry says.
   *
   * Compared as text because the column's type is the table's business: the client
   * sends `sdk` as a number and a `text` column hands it back as a string, and a
   * row differing only in that is the same row. A field the entry does not carry
   * says nothing about the device, so it cannot be what makes the record stale.
   */
  fun isUnchanged(stored: JsonObject, entry: JsonObject, kept: List<String>): Boolean {
    return kept.all { field ->
      val incoming = entry.getValue(field)?.toString()
      incoming == null || incoming == stored.getValue(field)?.toString()
    }
  }
}
