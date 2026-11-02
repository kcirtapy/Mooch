package com.mooch.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.CalendarContract
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.outlined.BookmarkBorder
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Event
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.automirrored.outlined.List
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mooch.R
import com.mooch.data.Fmt
import com.mooch.data.MoochEvent
import com.mooch.data.Row as FeedRow
import com.mooch.data.buildRows
import kotlinx.coroutines.delay
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private val SOURCE_NAMES = mapOf(
    "jumbolife" to "JumboLife calendar",
    "email" to "Newsletters",
    "instagram" to "Instagram",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EventListScreen(
    state: UiState,
    onRefresh: () -> Unit,
    onOpenSettings: () -> Unit,
    onQuery: (String) -> Unit,
    onTab: (FeedTab) -> Unit,
    onToggleSource: (String) -> Unit,
    onResetSources: () -> Unit,
    onToggleSaved: (String) -> Unit,
    listState: LazyListState,
    bottomBar: @Composable () -> Unit,
) {
    val context = LocalContext.current
    val zone = remember(state.feed?.timezone) {
        runCatching { ZoneId.of(state.feed?.timezone ?: "America/New_York") }
            .getOrDefault(ZoneId.systemDefault())
    }

    // Re-tick every 30s so "in 40 min" stays honest while the app is open.
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(30_000)
            now = Instant.now()
        }
    }

    var selected by remember { mutableStateOf<MoochEvent?>(null) }
    var showFilters by remember { mutableStateOf(false) }
    // List or month grid. Saveable so it survives rotation and trips to Settings.
    var calendarMode by rememberSaveable { mutableStateOf(false) }

    val cutoff = now.minus(Duration.ofHours(2))
    val visible = state.visibleEvents().filter { e -> e.start?.isAfter(cutoff) ?: true }
    val rows = remember(visible, now, zone) { buildRows(visible, zone, now) }
    val hasAnyEvents = state.feed?.events?.isNotEmpty() == true

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopArea(
                query = state.query,
                onQuery = onQuery,
                tab = state.tab,
                onTab = onTab,
                savedCount = state.settings.savedIds.size,
                filtersActive = state.filtersActive,
                onOpenFilters = { showFilters = true },
                calendarMode = calendarMode,
                onToggleView = { calendarMode = !calendarMode },
            )
        },
        bottomBar = bottomBar,
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.loading,
            onRefresh = onRefresh,
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            if (calendarMode) {
                CalendarView(
                    events = visible,
                    zone = zone,
                    now = now,
                    savedIds = state.settings.savedIds,
                    onOpen = { selected = it },
                    onToggleSaved = onToggleSaved,
                )
            } else LazyColumn(
                modifier = Modifier.fillMaxSize(),
                state = listState,
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 6.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                state.error?.let { message ->
                    item(key = "error") {
                        ErrorBanner(message, state.stale && hasAnyEvents, onOpenSettings)
                    }
                }

                if (rows.isEmpty() && (state.error == null || !hasAnyEvents)) {
                    item(key = "empty") {
                        EmptyState(
                            configured = state.settings.isConfigured,
                            hasAnyEvents = hasAnyEvents,
                            tab = state.tab,
                            onOpenSettings = onOpenSettings,
                            onClear = {
                                onQuery("")
                                onResetSources()
                                onTab(FeedTab.All)
                            },
                        )
                    }
                }

                items(rows, key = { row ->
                    when (row) {
                        is FeedRow.Header -> "h-${row.label}"
                        is FeedRow.Event -> row.event.id
                    }
                }) { row ->
                    when (row) {
                        is FeedRow.Header -> DayLabel(row.label, row.isToday)
                        is FeedRow.Event -> EventCard(
                            event = row.event,
                            zone = zone,
                            now = now,
                            saved = row.event.id in state.settings.savedIds,
                            onClick = { selected = row.event },
                            onToggleSaved = { onToggleSaved(row.event.id) },
                        )
                    }
                }

                state.feed?.generatedAt?.let { stamp ->
                    item(key = "footer") { Footer(stamp, zone, state.stale) }
                }
            }
        }
    }

    selected?.let { event ->
        EventSheet(
            event = event,
            zone = zone,
            now = now,
            saved = event.id in state.settings.savedIds,
            onToggleSaved = { onToggleSaved(event.id) },
            onOpenUrl = { openUrl(context, event.url) },
            onAddToCalendar = { addToCalendar(context, event) },
            onDismiss = { selected = null },
        )
    }

    if (showFilters) {
        FilterSheet(
            sources = state.sources,
            onToggle = onToggleSource,
            onReset = onResetSources,
            onDismiss = { showFilters = false },
        )
    }
}

// -- top: search and tabs -----------------------------------------------------

@Composable
private fun TopArea(
    query: String,
    onQuery: (String) -> Unit,
    tab: FeedTab,
    onTab: (FeedTab) -> Unit,
    savedCount: Int,
    filtersActive: Boolean,
    onOpenFilters: () -> Unit,
    calendarMode: Boolean,
    onToggleView: () -> Unit,
) {
    val focus = LocalFocusManager.current
    val colors = MaterialTheme.colorScheme

    Column(
        Modifier
            .fillMaxWidth()
            .background(colors.background)
            .statusBarsPadding()
            .padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 12.dp),
    ) {
        OutlinedTextField(
            value = query,
            onValueChange = onQuery,
            modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
            placeholder = { Text("Search food, clubs, places", style = MaterialTheme.typography.bodyMedium) },
            leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null) },
            trailingIcon = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (query.isNotEmpty()) {
                        IconButton(onClick = { onQuery("") }) {
                            Icon(Icons.Outlined.Close, contentDescription = "Clear search")
                        }
                    }
                    IconButton(onClick = onOpenFilters) {
                        Box {
                            Icon(
                                Icons.Outlined.Tune,
                                contentDescription = "Filter sources",
                                tint = if (filtersActive) colors.primary else colors.onSurfaceVariant,
                            )
                            if (filtersActive) {
                                Box(
                                    Modifier
                                        .align(Alignment.TopEnd)
                                        .size(7.dp)
                                        .clip(CircleShape)
                                        .background(colors.primary),
                                )
                            }
                        }
                    }
                }
            },
            singleLine = true,
            textStyle = MaterialTheme.typography.bodyMedium,
            shape = RoundedCornerShape(16.dp),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { focus.clearFocus() }),
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = colors.surface,
                unfocusedContainerColor = colors.surface,
                focusedBorderColor = colors.primary.copy(alpha = 0.55f),
                unfocusedBorderColor = colors.outline,
                focusedLeadingIconColor = colors.onSurfaceVariant,
                unfocusedLeadingIconColor = colors.onSurfaceVariant,
                focusedPlaceholderColor = colors.onSurfaceVariant,
                unfocusedPlaceholderColor = colors.onSurfaceVariant,
                cursorColor = colors.primary,
            ),
        )

        Spacer(Modifier.height(12.dp))

        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pill("All events", tab == FeedTab.All, onClick = { onTab(FeedTab.All) })
                Pill(if (savedCount > 0) "Saved · $savedCount" else "Saved", tab == FeedTab.Saved, onClick = { onTab(FeedTab.Saved) })
            }
            // List / calendar switch, tucked at the right of the pills.
            IconButton(onClick = onToggleView, modifier = Modifier.align(Alignment.CenterEnd)) {
                Icon(
                    if (calendarMode) Icons.AutoMirrored.Outlined.List else Icons.Outlined.CalendarMonth,
                    contentDescription = if (calendarMode) "Show as list" else "Show as calendar",
                    tint = if (calendarMode) colors.primary else colors.onSurfaceVariant,
                )
            }
        }
    }
}

/** A rounded toggle: solid red when selected, outlined when not. Shared with Settings. */
@Composable
internal fun Pill(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    Box(
        modifier
            .clip(CircleShape)
            .background(if (selected) colors.primary else colors.surface)
            .border(1.dp, if (selected) colors.primary else colors.outline, CircleShape)
            .clickable(onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = if (selected) colors.onPrimary else colors.onSurface,
            maxLines = 1,
        )
    }
}

// -- feed items ---------------------------------------------------------------

@Composable
private fun DayLabel(label: String, isToday: Boolean) {
    Text(
        label,
        style = MaterialTheme.typography.titleSmall,
        color = if (isToday) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(start = 4.dp, top = 6.dp),
    )
}

@Composable
internal fun EventCard(
    event: MoochEvent,
    zone: ZoneId,
    now: Instant,
    saved: Boolean,
    onClick: () -> Unit,
    onToggleSaved: () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    Card(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = colors.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.5.dp),
    ) {
        // Where the reference shows a photo: the food itself, big.
        Box(
            Modifier
                .fillMaxWidth()
                .height(112.dp)
                .background(colors.primaryContainer),
        ) {
            Text(
                foodLabel(event),
                style = MaterialTheme.typography.titleLarge.copy(fontSize = 25.sp, lineHeight = 29.sp),
                color = colors.onPrimaryContainer,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .padding(start = 16.dp, end = 16.dp, bottom = 14.dp),
            )
            HostChip(
                event.author?.takeIf { it.isNotBlank() } ?: event.sourceLabel,
                Modifier.align(Alignment.TopStart).padding(12.dp),
            )
            SaveToggle(saved, onToggleSaved, Modifier.align(Alignment.TopEnd).padding(6.dp))
        }

        Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Outlined.Schedule,
                    contentDescription = null,
                    tint = colors.onSurfaceVariant,
                    modifier = Modifier.size(15.dp),
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    whenShort(event, zone),
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                if (event.start != null) {
                    Text(
                        Fmt.relative(event.start, now),
                        style = MaterialTheme.typography.labelMedium,
                        color = colors.primary,
                    )
                }
            }

            Spacer(Modifier.height(6.dp))
            val location = event.location?.takeIf { it.isNotBlank() }
            // Like the reference: the place is the headline, since that's where you're going.
            Text(
                location ?: event.title,
                style = MaterialTheme.typography.titleMedium,
                color = colors.onSurface,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (location != null) {
                Spacer(Modifier.height(2.dp))
                Text(
                    event.title,
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            if (isUncertain(event)) {
                Spacer(Modifier.height(10.dp))
                MaybeNote(event.reason.orEmpty())
            }
        }
    }
}

@Composable
private fun HostChip(name: String, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    Row(
        modifier
            .clip(CircleShape)
            .background(colors.surface)
            .padding(start = 4.dp, end = 11.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(22.dp).clip(CircleShape).background(colors.primary),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                name.trimStart('@').firstOrNull()?.uppercase() ?: "?",
                style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                color = colors.onPrimary,
            )
        }
        Spacer(Modifier.width(6.dp))
        Text(
            name,
            style = MaterialTheme.typography.labelSmall,
            color = colors.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.widthIn(max = 200.dp),
        )
    }
}

@Composable
private fun SaveToggle(saved: Boolean, onToggle: () -> Unit, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    IconButton(onClick = onToggle, modifier = modifier) {
        Box(
            Modifier.size(34.dp).clip(CircleShape).background(colors.surface),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                if (saved) Icons.Filled.Bookmark else Icons.Outlined.BookmarkBorder,
                contentDescription = if (saved) "Unsave" else "Save",
                tint = if (saved) colors.primary else colors.onSurfaceVariant,
                modifier = Modifier.size(19.dp),
            )
        }
    }
}

@Composable
private fun MaybeNote(reason: String) {
    val colors = MaterialTheme.colorScheme
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(colors.tertiaryContainer)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            "Maybe",
            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
            color = colors.tertiary,
        )
        Spacer(Modifier.width(8.dp))
        Text(
            reason.ifBlank { "Not sure the food is free." },
            style = MaterialTheme.typography.labelSmall,
            color = colors.onSurface.copy(alpha = 0.75f),
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun ErrorBanner(message: String, hasStaleData: Boolean, onOpenSettings: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(colors.surface)
            .border(1.dp, colors.outline, RoundedCornerShape(16.dp))
            .padding(start = 16.dp, end = 8.dp, top = 14.dp, bottom = 4.dp),
    ) {
        Text(message, style = MaterialTheme.typography.bodyMedium, color = colors.onSurface)
        if (hasStaleData) {
            Spacer(Modifier.height(3.dp))
            Text(
                "Showing the last list that came through.",
                style = MaterialTheme.typography.labelSmall,
                color = colors.onSurfaceVariant,
            )
        }
        TextButton(onClick = onOpenSettings, contentPadding = PaddingValues(horizontal = 0.dp)) {
            Text("Connection settings", style = MaterialTheme.typography.labelLarge, color = colors.primary)
        }
    }
}

@Composable
private fun EmptyState(
    configured: Boolean,
    hasAnyEvents: Boolean,
    tab: FeedTab,
    onOpenSettings: () -> Unit,
    onClear: () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    val (title, body, action) = when {
        !configured -> Triple(
            "Point Mooch at your laptop",
            "Run serve.bat there, then add the address and token in Settings.",
            "Open settings" to onOpenSettings,
        )
        tab == FeedTab.Saved -> Triple(
            "Nothing saved yet",
            "Tap the bookmark on any event to keep it here.",
            null,
        )
        hasAnyEvents -> Triple(
            "Nothing matches",
            "Try a different search, or turn more sources back on.",
            "Clear filters" to onClear,
        )
        else -> Triple(
            "No free food on the calendar",
            "Mooch is watching. Pull down or tap refresh to check again.",
            null,
        )
    }

    Column(
        Modifier.fillMaxWidth().padding(top = 36.dp, start = 24.dp, end = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Image(
            painter = painterResource(R.mipmap.ic_launcher_foreground),
            contentDescription = null,
            modifier = Modifier.size(150.dp),
        )
        Text(title, style = MaterialTheme.typography.titleLarge, color = colors.onBackground, textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        Text(body, style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant, textAlign = TextAlign.Center)
        action?.let { (label, onClick) ->
            Spacer(Modifier.height(18.dp))
            PillButton(label, icon = null, filled = true, onClick = onClick, modifier = Modifier.widthIn(min = 200.dp))
        }
    }
}

@Composable
private fun Footer(generatedAt: String, zone: ZoneId, stale: Boolean) {
    val stamp = runCatching { Fmt.time(Instant.parse(generatedAt), zone) }.getOrDefault("—")
    Text(
        if (stale) "Last reached the laptop at $stamp" else "Laptop last checked at $stamp",
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center,
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
    )
}

// -- sheets -------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EventSheet(
    event: MoochEvent,
    zone: ZoneId,
    now: Instant,
    saved: Boolean,
    onToggleSaved: () -> Unit,
    onOpenUrl: () -> Unit,
    onAddToCalendar: () -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = colors.surface,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 22.dp)
                .padding(bottom = 28.dp)
                .navigationBarsPadding(),
        ) {
            Text(foodLabel(event), style = MaterialTheme.typography.titleSmall, color = colors.primary)
            Spacer(Modifier.height(4.dp))
            Text(event.title, style = MaterialTheme.typography.headlineSmall, color = colors.onSurface)
            Spacer(Modifier.height(18.dp))

            InfoRow(Icons.Outlined.Schedule, whenLong(event, zone, now))
            event.location?.takeIf { it.isNotBlank() }?.let { InfoRow(Icons.Outlined.Place, it) }
            event.author?.takeIf { it.isNotBlank() }?.let { InfoRow(Icons.Outlined.Groups, it) }
            InfoRow(
                Icons.Outlined.Info,
                "From ${SOURCE_NAMES[event.source] ?: event.sourceLabel} · ${(event.confidence * 100).toInt()}% sure it's free",
            )

            if (isUncertain(event)) {
                Spacer(Modifier.height(6.dp))
                MaybeNote(event.reason.orEmpty())
            }

            Spacer(Modifier.height(22.dp))
            if (event.start != null) {
                PillButton("Add to calendar", Icons.Outlined.Event, filled = true, onClick = onAddToCalendar)
                Spacer(Modifier.height(10.dp))
            }
            if (!event.url.isNullOrBlank()) {
                PillButton("Open original", Icons.AutoMirrored.Outlined.OpenInNew, filled = false, onClick = onOpenUrl)
                Spacer(Modifier.height(10.dp))
            }
            PillButton(
                if (saved) "Saved" else "Save for later",
                if (saved) Icons.Filled.Bookmark else Icons.Outlined.BookmarkBorder,
                filled = false,
                onClick = onToggleSaved,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterSheet(
    sources: Set<String>,
    onToggle: (String) -> Unit,
    onReset: () -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = colors.surface,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 22.dp)
                .padding(bottom = 28.dp)
                .navigationBarsPadding(),
        ) {
            Text("Show events from", style = MaterialTheme.typography.titleLarge, color = colors.onSurface)
            Spacer(Modifier.height(10.dp))
            ALL_SOURCES.forEach { source ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .clickable { onToggle(source) }
                        .padding(vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        SOURCE_NAMES[source] ?: source,
                        style = MaterialTheme.typography.bodyLarge,
                        color = colors.onSurface,
                        modifier = Modifier.weight(1f),
                    )
                    Switch(checked = source in sources, onCheckedChange = { onToggle(source) })
                }
            }
            if (sources.size < ALL_SOURCES.size) {
                Spacer(Modifier.height(8.dp))
                PillButton("Show everything", icon = null, filled = false, onClick = onReset)
            }
        }
    }
}

@Composable
private fun InfoRow(icon: ImageVector, text: String) {
    Row(Modifier.padding(vertical = 7.dp), verticalAlignment = Alignment.Top) {
        Icon(
            icon,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(20.dp).padding(top = 1.dp),
        )
        Spacer(Modifier.width(12.dp))
        Text(text, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
private fun PillButton(
    label: String,
    icon: ImageVector?,
    filled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier.fillMaxWidth(),
) {
    val colors = MaterialTheme.colorScheme
    val content: @Composable () -> Unit = {
        if (icon != null) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(19.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(label, style = MaterialTheme.typography.labelLarge)
    }
    if (filled) {
        Button(
            onClick = onClick,
            modifier = modifier.height(52.dp),
            shape = CircleShape,
            colors = ButtonDefaults.buttonColors(containerColor = colors.primary, contentColor = colors.onPrimary),
        ) { content() }
    } else {
        OutlinedButton(
            onClick = onClick,
            modifier = modifier.height(52.dp),
            shape = CircleShape,
            border = BorderStroke(1.dp, colors.outline),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = colors.onSurface),
        ) { content() }
    }
}

// -- helpers ------------------------------------------------------------------

private fun isUncertain(e: MoochEvent) = e.confidence < 0.75 && !e.reason.isNullOrBlank()

private fun foodLabel(e: MoochEvent): String =
    e.food?.takeIf { it.isNotBlank() }?.replaceFirstChar { it.uppercase() } ?: "Free food"

private val dayShort = DateTimeFormatter.ofPattern("EEE, MMM d", Locale.US)
private val dayLong = DateTimeFormatter.ofPattern("EEEE, MMMM d", Locale.US)

private fun whenShort(e: MoochEvent, zone: ZoneId): String {
    val start = e.start ?: return "No date given · seen ${Fmt.shortDate(e.posted, zone)}"
    return "${start.atZone(zone).format(dayShort)} · ${Fmt.time(start, zone)}"
}

private fun whenLong(e: MoochEvent, zone: ZoneId, now: Instant): String {
    val start = e.start ?: return "No date given"
    return "${start.atZone(zone).format(dayLong)} at ${Fmt.time(start, zone)} (${Fmt.relative(start, now)})"
}

private fun openUrl(context: Context, url: String?) {
    if (url.isNullOrBlank()) return
    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
}

/** Hands the event to whatever calendar app is installed; no permission needed. */
private fun addToCalendar(context: Context, e: MoochEvent) {
    val start = e.start ?: return
    val intent = Intent(Intent.ACTION_INSERT).apply {
        data = CalendarContract.Events.CONTENT_URI
        putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, start.toEpochMilli())
        putExtra(CalendarContract.EXTRA_EVENT_END_TIME, start.plus(Duration.ofHours(1)).toEpochMilli())
        putExtra(CalendarContract.Events.TITLE, "${foodLabel(e)}: ${e.title}")
        e.location?.takeIf { it.isNotBlank() }?.let { putExtra(CalendarContract.Events.EVENT_LOCATION, it) }
        putExtra(
            CalendarContract.Events.DESCRIPTION,
            listOfNotNull(e.author, e.url, "Found by Mooch").joinToString("\n"),
        )
    }
    runCatching { context.startActivity(intent) }
}
