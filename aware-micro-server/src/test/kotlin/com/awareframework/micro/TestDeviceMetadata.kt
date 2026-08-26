package com.awareframework.micro

import io.vertx.core.json.JsonObject
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TestDeviceMetadata {

  /** The Android table's columns: one per field, and no `data` to put a blob in. */
  private val androidColumns = setOf(
    "_id", "timestamp", "device_id", "board", "device", "build_id", "hardware",
    "manufacturer", "model", "product", "release", "sdk", "label"
  )

  /** The iOS table's columns, which keep a row whole. */
  private val iosColumns = setOf("_id", "timestamp", "device_id", "data")

  /** What the Android client actually reports about itself. */
  private fun androidReport(): JsonObject = JsonObject()
    .put("board", "goldfish_arm64")
    .put("device", "emulator64_arm64")
    .put("build_id", "QSR1.211112.011")
    .put("hardware", "ranchu")
    .put("manufacturer", "Google")
    .put("model", "Android SDK built for arm64")
    .put("product", "sdk_gphone64_arm64")
    .put("release", "10")
    .put("sdk", 29)
    .put("label", "emulator-test")

  @Test
  fun keepsEveryFieldWhereTheTableStoresTheRowWhole() {
    assertEquals(DeviceMetadata.fields, DeviceMetadata.fieldsKeptBy(iosColumns))
  }

  @Test
  fun keepsOnlyTheFieldsAColumnarTableHasColumnsFor() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    assertFalse(kept.contains("brand"))
    assertFalse(kept.contains("serial"))
    assertFalse(kept.contains("release_type"))
    assertTrue(kept.contains("model"))
    assertTrue(kept.contains("label"))
  }

  @Test
  fun readsAnAndroidReportAsCompleteWithoutTheColumnsTheTableHasNot() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    assertTrue(DeviceMetadata.isComplete(androidReport(), kept))
  }

  @Test
  fun readsTheSameReportAsIncompleteWhereTheTableKeepsMore() {
    val kept = DeviceMetadata.fieldsKeptBy(iosColumns)
    assertFalse(DeviceMetadata.isComplete(androidReport(), kept))
  }

  @Test
  fun countsABlankAnswerAsNoAnswer() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    assertFalse(DeviceMetadata.isComplete(androidReport().put("label", ""), kept))
  }

  @Test
  fun treatsARepeatedReportAsUnchanged() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    assertTrue(DeviceMetadata.isUnchanged(androidReport(), androidReport(), kept))
  }

  @Test
  fun treatsANumberAndItsTextAsTheSameAnswer() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    val stored = androidReport().put("sdk", "29")
    assertTrue(DeviceMetadata.isUnchanged(stored, androidReport(), kept))
  }

  @Test
  fun noticesTheParticipantLabelChanging() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    val renamed = androidReport().put("label", "participant-07")
    assertFalse(DeviceMetadata.isUnchanged(androidReport(), renamed, kept))
  }

  @Test
  fun ignoresAFieldTheReportDoesNotCarry() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    val partial = androidReport()
    partial.remove("model")
    assertTrue(DeviceMetadata.isUnchanged(androidReport(), partial, kept))
  }

  @Test
  fun noticesAFieldArrivingForTheFirstTime() {
    val kept = DeviceMetadata.fieldsKeptBy(androidColumns)
    val blank = androidReport().put("label", "")
    assertFalse(DeviceMetadata.isUnchanged(blank, androidReport(), kept))
  }
}
