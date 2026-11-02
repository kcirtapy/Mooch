package com.mooch.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

/** Mirrors the JSON written by `mooch serve` / `mooch export`. */
@Serializable
data class Feed(
    val version: Int = 1,
    val generatedAt: String? = null,
    val timezone: String = "America/New_York",
    val events: List<MoochEvent> = emptyList(),
)

@Serializable
data class MoochEvent(
    val id: String,
    val title: String,
    val food: String? = null,
    val startsAt: String? = null,
    val location: String? = null,
    val author: String? = null,
    val source: String = "unknown",
    val url: String? = null,
    val confidence: Double = 0.0,
    val reason: String? = null,
    @SerialName("postedAt") val postedAt: String? = null,
) {
    val start: Instant? get() = parseInstant(startsAt)
    val posted: Instant? get() = parseInstant(postedAt)

    /** Within the next six hours: worth flagging in the list. */
    fun isSoon(now: Instant = Instant.now()): Boolean {
        val s = start ?: return false
        val seconds = Duration.between(now, s).seconds
        return seconds in 0..(6 * 3600)
    }

    fun isPast(now: Instant = Instant.now()): Boolean {
        val s = start ?: return false
        return s.isBefore(now)
    }

    val sourceLabel: String
        get() = when (source) {
            "instagram" -> "Instagram"
            "email" -> "Newsletter"
            "jumbolife" -> "JumboLife"
            else -> source.replaceFirstChar { it.uppercase() }
        }

    /** "Halligan 102, @tuftsacm, Instagram" — whatever we actually know. */
    fun metaLine(): String =
        listOfNotNull(
            location?.takeIf { it.isNotBlank() },
            author?.takeIf { it.isNotBlank() },
            sourceLabel,
        ).joinToString(", ")
}

private fun parseInstant(raw: String?): Instant? {
    if (raw.isNullOrBlank()) return null
    return runCatching { Instant.parse(raw) }
        .recoverCatching { ZonedDateTime.parse(raw).toInstant() }
        .getOrNull()
}

// -- formatting ------------------------------------------------------------

object Fmt {
    private val clock = DateTimeFormatter.ofPattern("h:mm a", Locale.US)

    /** "in 40 min", "in 3 hours", "tomorrow", "in 5 days". */
    fun relative(start: Instant?, now: Instant = Instant.now()): String {
        if (start == null) return "no date given"
        val seconds = Duration.between(now, start).seconds
        if (seconds < 0) return "happening now"
        val minutes = seconds / 60
        if (minutes < 60) return "in $minutes min"
        val hours = minutes / 60
        if (hours < 24) return if (hours == 1L) "in 1 hour" else "in $hours hours"
        val days = hours / 24
        return if (days == 1L) "tomorrow" else "in $days days"
    }

    fun time(start: Instant?, zone: ZoneId): String =
        start?.atZone(zone)?.format(clock)?.lowercase(Locale.US) ?: "—"

    /** Section heading: "Today", "Tomorrow", or "Saturday, September 19". */
    fun dayLabel(start: Instant, zone: ZoneId, now: Instant = Instant.now()): String {
        val day = start.atZone(zone).toLocalDate()
        val today = now.atZone(zone).toLocalDate()
        return when (day) {
            today -> "Today"
            today.plusDays(1) -> "Tomorrow"
            else -> "${day.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.US)}, " +
                "${day.month.getDisplayName(TextStyle.FULL, Locale.US)} ${day.dayOfMonth}"
        }
    }

    fun dayKey(start: Instant, zone: ZoneId): LocalDate = start.atZone(zone).toLocalDate()

    fun shortDate(instant: Instant?, zone: ZoneId): String {
        val d = instant?.atZone(zone)?.toLocalDate() ?: return "—"
        return "${d.monthValue}/${d.dayOfMonth}"
    }
}

/** What the list screen renders: either a dated event or a day heading. */
sealed interface Row {
    data class Header(val label: String, val isToday: Boolean) : Row
    data class Event(val event: MoochEvent) : Row
}

/**
 * Groups events into day sections. The soonest dated event is pulled out as the
 * hero by the caller; undated ones fall to their own section at the bottom.
 */
fun buildRows(events: List<MoochEvent>, zone: ZoneId, now: Instant = Instant.now()): List<Row> {
    val rows = mutableListOf<Row>()
    val dated = events.filter { it.start != null }.sortedBy { it.start }
    val undated = events.filter { it.start == null }

    var currentDay: LocalDate? = null
    dated.forEach { event ->
        val key = Fmt.dayKey(event.start!!, zone)
        if (key != currentDay) {
            val label = Fmt.dayLabel(event.start!!, zone, now)
            rows.add(Row.Header(label, label == "Today"))
            currentDay = key
        }
        rows.add(Row.Event(event))
    }

    if (undated.isNotEmpty()) {
        rows.add(Row.Header("No date attached", false))
        undated.sortedByDescending { it.posted }.forEach { rows.add(Row.Event(it)) }
    }
    return rows
}

// -- card display ------------------------------------------------------------

private val FOOD_EMOJI = listOf(
    "boba|bubble tea|milk tea" to "🧋",
    "pizza" to "🍕",
    "bagel" to "🥯",
    "donut|doughnut" to "🍩",
    "burger" to "🍔",
    "taco|burrito|quesadilla" to "🌮",
    "sushi" to "🍣",
    "dumpling|bao|momo" to "🥟",
    "ice cream|gelato|froyo" to "🍦",
    "cookie" to "🍪",
    "cupcake|cake|brownie" to "🧁",
    "coffee|latte|espresso" to "☕",
    "tea" to "🍵",
    "sandwich|sub|hoagie" to "🥪",
    "fries" to "🍟",
    "chicken|wings" to "🍗",
    "ramen|noodle|pho|pasta" to "🍜",
    "curry|biryani|rice" to "🍛",
    "popcorn" to "🍿",
    "chocolate|candy|sweets" to "🍫",
    "salad" to "🥗",
    "pancake|waffle|brunch|breakfast" to "🥞",
    "bbq|barbecue|cookout|grill" to "🍖",
    "fruit|apple|cider" to "🍎",
).map { (words, emoji) -> Regex("\\b(?:$words)s?\\b", RegexOption.IGNORE_CASE) to emoji }

/** A stand-in for a food photo, picked from what's being served. */
fun MoochEvent.foodEmoji(): String {
    val haystack = listOfNotNull(food, title).joinToString(" ")
    return FOOD_EMOJI.firstOrNull { (re, _) -> re.containsMatchIn(haystack) }?.second ?: "🍽️"
}

/** The big line on a card: where to go, or what it is when the venue is unknown. */
fun MoochEvent.headline(): String = location?.takeIf { it.isNotBlank() } ?: title

/** The line under it: what's served, and the event when the headline was the venue. */
fun MoochEvent.subline(): String {
    val served = food?.takeIf { it.isNotBlank() }?.replaceFirstChar { it.uppercase() } ?: "Free food"
    return if (location.isNullOrBlank()) served else "$served · $title"
}

/** The hosting club or account, falling back to where the listing came from. */
fun MoochEvent.host(): String = author?.takeIf { it.isNotBlank() } ?: sourceLabel

val MoochEvent.isUncertain: Boolean get() = confidence < 0.75

/** "Today · 6:00 pm", "Tomorrow · 6:00 pm", "Thu, Oct 2 · 6:00 pm". */
fun Fmt.whenLabel(start: Instant?, zone: ZoneId, now: Instant = Instant.now()): String {
    if (start == null) return "No date given"
    val day = start.atZone(zone).toLocalDate()
    val today = now.atZone(zone).toLocalDate()
    val dayPart = when (day) {
        today -> "Today"
        today.plusDays(1) -> "Tomorrow"
        else -> "${day.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.US)}, " +
            "${day.month.getDisplayName(TextStyle.SHORT, Locale.US)} ${day.dayOfMonth}"
    }
    return "$dayPart · ${time(start, zone)}"
}
