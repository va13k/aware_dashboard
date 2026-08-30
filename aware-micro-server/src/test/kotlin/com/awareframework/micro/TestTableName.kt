package com.awareframework.micro

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class TestTableName {

  @Test
  fun quotesATableAnAwareClientWritesTo() {
    assertEquals("`accelerometer`", TableName.quoted("accelerometer"))
    assertEquals("`aware_device`", TableName.quoted("aware_device"))
  }

  /**
   * A backtick closes the quoting, and everything after it is read as SQL. The
   * name is the only part of the statement a value cannot be bound into, so this
   * is where a query segment would arrive if anywhere.
   */
  @Test
  fun refusesANameCarryingABacktick() {
    assertNull(
      TableName.quoted("accelerometer` WHERE 1=1 UNION SELECT * FROM mysql.user -- ")
    )
  }

  @Test
  fun refusesANameCarryingAQuoteASpaceOrASeparator() {
    assertNull(TableName.quoted("accelerometer'"))
    assertNull(TableName.quoted("two words"))
    assertNull(TableName.quoted("aware_android.accelerometer"))
  }

  @Test
  fun refusesANameNoTableCouldHave() {
    assertNull(TableName.quoted(""))
    assertNull(TableName.quoted(null))
    assertNull(TableName.quoted("a".repeat(65)))
  }
}
