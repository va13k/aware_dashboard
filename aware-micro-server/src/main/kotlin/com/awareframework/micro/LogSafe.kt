package com.awareframework.micro

import io.vertx.core.json.JsonArray
import io.vertx.core.json.JsonObject

/**
 * What a request or a study config may say in the log.
 *
 * Three things ended up there that should not have. The study key, which is the
 * credential a phone joins and writes with, sits in the path of every request. A
 * participant's sensor rows arrive as request parameters, so logging the
 * parameters copied the data itself out of the study database and into container
 * logs that no retention or consent story covers. And the served study config
 * carries the key again along with third-party plugin credentials.
 *
 * A log line still has to be useful for reading what the server is doing, so this
 * keeps the shape and drops the contents: which route, which parameters, how big.
 */
object LogSafe {

  /** Stands in for anything withheld, so a reader can see that it was. */
  const val REDACTED = "<redacted>"

  /**
   * Parameter names without their values.
   *
   * The names are the useful part: they say which route was exercised and whether
   * a request arrived shaped as expected. The values are the participant's data.
   */
  fun paramNames(names: Iterable<String>): String {
    val listed = names.distinct().sorted()
    return if (listed.isEmpty()) "[]" else listed.joinToString(", ", "[", "]")
  }

  /**
   * A path with the study key taken out of it.
   *
   * Matched as a value rather than by position, so it is removed wherever it
   * appears --- the key sits in a different segment on the study route than on an
   * insert, and a future route could put it somewhere else again.
   */
  fun path(path: String, studyKey: String?): String {
    if (studyKey.isNullOrBlank()) {
      return path
    }
    return path.replace(studyKey, REDACTED)
  }

  /**
   * What a study config is, rather than what it contains.
   *
   * Counted rather than printed. The body is the thing worth withholding, and
   * "34 sensors, 17 plugins" answers the question the line was there to answer:
   * whether a config was assembled and served at all.
   */
  fun configSummary(config: JsonArray): String {
    if (config.isEmpty) {
      return "no study config"
    }
    val study = config.getJsonObject(0) ?: return "no study config"
    val sensors = study.getJsonArray("sensors")?.size() ?: 0
    val plugins = study.getJsonArray("plugins")?.size() ?: 0
    return "$sensors sensors, $plugins plugins"
  }

  /**
   * A join URL with its key removed, for the line that reports the QR contents.
   *
   * The QR code itself still carries the key --- that is what it is for. What
   * changes is that reading the log is no longer a way to obtain one.
   */
  fun joinUrl(url: String, studyKey: String?): String = path(url, studyKey)

  /** The study key a config declares, or null when it holds none. */
  fun studyKeyOf(study: JsonObject?): String? = study?.getString("study_key")
}
