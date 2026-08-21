package com.awareframework.micro

import io.vertx.core.json.JsonArray
import io.vertx.core.json.JsonObject
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TestLogSafe {

  private val studyKey = "9qFNcpdTs_CN"

  /**
   * The key sits in a different segment on the study route than on an insert, so
   * it is matched as a value rather than by position.
   */
  @Test
  fun takesTheStudyKeyOutOfAStudyPath() {
    val safe = LogSafe.path("/1/$studyKey", studyKey)

    assertFalse(safe.contains(studyKey))
    assertEquals("/1/${LogSafe.REDACTED}", safe)
  }

  @Test
  fun takesTheStudyKeyOutOfAnInsertPath() {
    val safe = LogSafe.path("/index.php/1/$studyKey/accelerometer/insert", studyKey)

    assertFalse(safe.contains(studyKey))
    // The route is still readable, which is what the line was there to say.
    assertTrue(safe.contains("accelerometer/insert"))
  }

  @Test
  fun leavesAPathAloneWhenNoStudyKeyIsKnown() {
    assertEquals("/1/anything", LogSafe.path("/1/anything", null))
    assertEquals("/1/anything", LogSafe.path("/1/anything", ""))
  }

  /**
   * A participant's sensor rows arrive as parameter values. The names say which
   * route was exercised and whether the request was shaped as expected, which is
   * the whole diagnostic value; the values are the data itself.
   */
  @Test
  fun keepsParameterNamesAndDropsTheirValues() {
    assertEquals("[data, device_id]", LogSafe.paramNames(listOf("device_id", "data")))
  }

  @Test
  fun reportsNoParametersRatherThanNothing() {
    assertEquals("[]", LogSafe.paramNames(emptyList()))
  }

  @Test
  fun countsARepeatedParameterOnce() {
    assertEquals("[data]", LogSafe.paramNames(listOf("data", "data")))
  }

  /**
   * The served config carries the study key and third-party plugin credentials,
   * so the line reports what the config is instead of what it holds.
   */
  @Test
  fun summarisesAStudyConfigRatherThanPrintingIt() {
    val study = JsonObject()
      .put("sensors", JsonArray().add(JsonObject().put("setting", "status_wifi")))
      .put(
        "plugins",
        JsonArray().add(
          JsonObject().put("plugin", "openweather").put("api_key", "secret-key")
        )
      )

    val summary = LogSafe.configSummary(JsonArray().add(study))

    assertEquals("1 sensors, 1 plugins", summary)
    assertFalse(summary.contains("secret-key"))
    assertFalse(summary.contains("status_wifi"))
  }

  @Test
  fun saysSoWhenThereIsNoStudyConfig() {
    assertEquals("no study config", LogSafe.configSummary(JsonArray()))
  }

  @Test
  fun readsTheStudyKeyFromAConfigOrReportsNone() {
    assertEquals(studyKey, LogSafe.studyKeyOf(JsonObject().put("study_key", studyKey)))
    assertEquals(null, LogSafe.studyKeyOf(JsonObject()))
    assertEquals(null, LogSafe.studyKeyOf(null))
  }

  /** The QR itself still carries the key; reading the log no longer yields one. */
  @Test
  fun takesTheKeyOutOfTheReportedJoinUrl() {
    val safe = LogSafe.joinUrl("http://host:80/1/$studyKey", studyKey)

    assertFalse(safe.contains(studyKey))
    assertTrue(safe.startsWith("http://host:80/1/"))
  }
}
