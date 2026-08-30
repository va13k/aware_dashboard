package com.awareframework.micro

/**
 * The one part of a request that reaches a statement as text rather than as a
 * parameter.
 *
 * MySQL parses an identifier before it binds anything, so a table name is quoted
 * into the statement itself while every value around it is passed through. The
 * backtick is what quotes it, which is why a name carrying one can close the
 * quoting and have the rest of the segment read as SQL. Held here to the
 * characters an AWARE table is named with, so the quoting closes where this says
 * it closes.
 */
object TableName {

  /** What MySQL will hold as an identifier, and the length it holds it to. */
  private val ALLOWED = Regex("^[A-Za-z0-9_]{1,64}\$")

  /**
   * The name quoted for a statement, or null for one that may not be addressed.
   *
   * Null rather than an escaped spelling: a name outside this shape addresses no
   * table on this server, so there is nothing to escape it into.
   */
  fun quoted(table: String?): String? {
    if (table == null || !ALLOWED.matches(table)) return null
    return "`$table`"
  }
}
