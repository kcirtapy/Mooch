package com.mooch.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.mooch.data.MoochEvent
import java.time.Instant
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private val monthTitle = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.US)
private val dayTitle = DateTimeFormatter.ofPattern("EEEE, MMMM d", Locale.US)

/**
 * A month grid with a dot on every day that has free food. Tapping a day lists
 * its events below, as the same cards the list view uses.
 */
@Composable
internal fun CalendarView(
    events: List<MoochEvent>,
    zone: ZoneId,
    now: Instant,
    savedIds: Set<String>,
    onOpen: (MoochEvent) -> Unit,
    onToggleSaved: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    val today = now.atZone(zone).toLocalDate()
    var month by remember { mutableStateOf(YearMonth.from(today)) }
    var selected by remember { mutableStateOf(today) }

    val byDay = remember(events, zone) {
        events.filter { it.start != null }.groupBy { it.start!!.atZone(zone).toLocalDate() }
    }
    val undatedCount = events.count { it.start == null }
    val dayEvents = byDay[selected].orEmpty().sortedBy { it.start }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 6.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item(key = "month") {
            Column(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(20.dp))
                    .background(colors.surface)
                    .padding(horizontal = 10.dp, vertical = 12.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { month = month.minusMonths(1) }) {
                        Icon(Icons.AutoMirrored.Outlined.KeyboardArrowLeft, contentDescription = "Previous month")
                    }
                    Text(
                        month.format(monthTitle),
                        style = MaterialTheme.typography.titleMedium,
                        color = colors.onSurface,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.weight(1f),
                    )
                    IconButton(onClick = { month = month.plusMonths(1) }) {
                        Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = "Next month")
                    }
                }
                Spacer(Modifier.height(6.dp))

                // Weekday initials, Sunday first like most US calendars.
                Row(Modifier.fillMaxWidth()) {
                    listOf("S", "M", "T", "W", "T", "F", "S").forEach {
                        Text(
                            it,
                            style = MaterialTheme.typography.labelSmall,
                            color = colors.onSurfaceVariant,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))

                val first = month.atDay(1)
                val gridStart = first.minusDays((first.dayOfWeek.value % 7).toLong())
                var weekStart = gridStart
                while (!weekStart.isAfter(month.atEndOfMonth())) {
                    Row(Modifier.fillMaxWidth()) {
                        for (i in 0 until 7) {
                            val date = weekStart.plusDays(i.toLong())
                            DayCell(
                                date = date,
                                inMonth = YearMonth.from(date) == month,
                                isToday = date == today,
                                isSelected = date == selected,
                                count = byDay[date]?.size ?: 0,
                                onClick = {
                                    selected = date
                                    if (YearMonth.from(date) != month) month = YearMonth.from(date)
                                },
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                    weekStart = weekStart.plusWeeks(1)
                }
            }
        }

        item(key = "day-title") {
            Text(
                if (selected == today) "Today" else selected.format(dayTitle),
                style = MaterialTheme.typography.titleSmall,
                color = if (selected == today) colors.primary else colors.onSurfaceVariant,
                modifier = Modifier.padding(start = 4.dp, top = 2.dp),
            )
        }

        if (dayEvents.isEmpty()) {
            item(key = "day-empty") {
                Text(
                    "No free food this day.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.onSurfaceVariant,
                    modifier = Modifier.padding(start = 4.dp),
                )
            }
        } else {
            items(dayEvents, key = { it.id }) { event ->
                EventCard(
                    event = event,
                    zone = zone,
                    now = now,
                    saved = event.id in savedIds,
                    onClick = { onOpen(event) },
                    onToggleSaved = { onToggleSaved(event.id) },
                )
            }
        }

        if (undatedCount > 0) {
            item(key = "undated-note") {
                Text(
                    "$undatedCount event${if (undatedCount == 1) "" else "s"} with no date " +
                        "${if (undatedCount == 1) "isn't" else "aren't"} on the calendar. Switch to the list to see them.",
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun DayCell(
    date: LocalDate,
    inMonth: Boolean,
    isToday: Boolean,
    isSelected: Boolean,
    count: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    val label = date.dayOfMonth.toString()
    Box(modifier.aspectRatio(1f).padding(3.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .fillMaxSize()
                .clip(CircleShape)
                .background(
                    when {
                        isSelected -> colors.primary
                        isToday -> colors.primaryContainer
                        else -> Color.Transparent
                    }
                )
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    label,
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontWeight = if (isToday || isSelected) FontWeight.Bold else FontWeight.Normal,
                    ),
                    color = when {
                        isSelected -> colors.onPrimary
                        !inMonth -> colors.onSurfaceVariant.copy(alpha = 0.5f)
                        else -> colors.onSurface
                    },
                )
                // One dot per event, up to three.
                Row(horizontalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.height(6.dp)) {
                    repeat(minOf(count, 3)) {
                        Box(
                            Modifier
                                .padding(top = 1.dp)
                                .size(5.dp)
                                .clip(CircleShape)
                                .background(if (isSelected) colors.onPrimary else colors.primary),
                        )
                    }
                }
            }
        }
    }
}
