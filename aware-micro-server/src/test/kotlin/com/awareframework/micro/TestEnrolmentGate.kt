package com.awareframework.micro

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TestEnrolmentGate {

  @Test
  fun storesWithoutReadingTheRegistryWhenTheGateIsOff() {
    assertFalse(
      EnrolmentGate.mustConsultRegistry(
        requireEnrolment = false,
        table = "accelerometer",
        alreadyEnrolled = false
      )
    )
  }

  @Test
  fun readsTheRegistryForAnUnknownDeviceWhenTheGateIsOn() {
    assertTrue(
      EnrolmentGate.mustConsultRegistry(
        requireEnrolment = true,
        table = "accelerometer",
        alreadyEnrolled = false
      )
    )
  }

  @Test
  fun readsTheRegistryOncePerDevice() {
    assertFalse(
      EnrolmentGate.mustConsultRegistry(
        requireEnrolment = true,
        table = "accelerometer",
        alreadyEnrolled = true
      )
    )
  }

  /**
   * The study log is what every enrolment window is derived from, so a write to it
   * is stored on its own terms. Reading the registry first would refuse the join
   * event that fills the registry, and no device would ever hold a window.
   */
  @Test
  fun storesTheStudyLogWithoutReadingTheRegistry() {
    assertFalse(
      EnrolmentGate.mustConsultRegistry(
        requireEnrolment = true,
        table = "aware_studies",
        alreadyEnrolled = false
      )
    )
  }

  @Test
  fun readsTheRegistryForDeviceMetadata() {
    assertTrue(
      EnrolmentGate.mustConsultRegistry(
        requireEnrolment = true,
        table = "aware_device",
        alreadyEnrolled = false
      )
    )
  }

  /**
   * A window the study accounts for is one the phone reported or a researcher
   * entered. `first_data` is inferred from the presence of data, so a device
   * holding only that has no claim to membership and is absent from the list.
   */
  @Test
  fun countsOnlyTheJoinSourcesTheStudyAccountsFor() {
    assertEquals("'study_event', 'manual'", EnrolmentGate.joinSourceList)
  }
}
