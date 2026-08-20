package com.awareframework.micro

/**
 * The rule deciding whether a batch may be stored before the enrolment registry
 * has been read.
 *
 * `device_enrolment` holds one row per stretch of time a device was in the study.
 * A window whose `join_source` is `study_event` or `manual` is one the study
 * itself accounts for: the phone reported joining, or a researcher entered it. A
 * window marked `first_data` is inferred from the presence of data, so it says
 * that rows arrived and nothing about membership.
 *
 * Membership is read as having joined at some point, not as being inside an open
 * window now. A device that left the study keeps the window it earned, so its
 * remaining data is stored and a phone that enrols again is admitted on the same
 * evidence as the first time.
 */
object EnrolmentGate {

  /** The `join_source` values the study accounts for, as a SQL list literal. */
  val joinSourceList = listOf("study_event", "manual").joinToString(", ") { "'$it'" }

  /**
   * Tables carrying the evidence of joining.
   *
   * `aware_studies` is the phone's own study log, and every enrolment window is
   * derived from it. A write to it is what makes a device known, so it is stored
   * on its own terms: reading the registry first would refuse the join event that
   * fills the registry, and a phone that joined correctly would hold no window
   * and have no way to earn one.
   */
  val membershipTables = setOf("aware_studies")

  /**
   * Whether the registry has to be read before this batch is stored.
   *
   * `alreadyEnrolled` is a device whose window was read on an earlier batch. Only
   * a positive answer is remembered, so a device that enrols after being refused
   * is admitted by its next batch instead of waiting for anything to expire.
   */
  fun mustConsultRegistry(
    requireEnrolment: Boolean,
    table: String,
    alreadyEnrolled: Boolean
  ): Boolean {
    if (!requireEnrolment) {
      return false
    }
    if (table in membershipTables) {
      return false
    }
    return !alreadyEnrolled
  }
}
