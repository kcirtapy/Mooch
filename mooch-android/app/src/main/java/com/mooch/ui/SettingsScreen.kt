package com.mooch.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.mooch.data.ThemeMode
import kotlin.math.roundToInt

@Composable
fun SettingsScreen(
    state: UiState,
    onSave: (String, String) -> Unit,
    onToggleNotifications: (Boolean) -> Unit,
    onMinConfidence: (Float) -> Unit,
    onThemeMode: (ThemeMode) -> Unit,
    bottomBar: @Composable () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    var url by remember(state.settings.serverUrl) { mutableStateOf(state.settings.serverUrl) }
    var token by remember(state.settings.token) { mutableStateOf(state.settings.token) }
    var confidence by remember(state.settings.minConfidence) {
        mutableFloatStateOf(state.settings.minConfidence)
    }

    Scaffold(
        containerColor = colors.background,
        topBar = {
            // A plain page title: Settings is a tab, so there's nothing to go back to.
            Text(
                "Settings",
                style = MaterialTheme.typography.headlineSmall,
                color = colors.onBackground,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(colors.background)
                    .statusBarsPadding()
                    .padding(start = 20.dp, end = 20.dp, top = 14.dp, bottom = 2.dp),
            )
        },
        bottomBar = bottomBar,
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
        ) {
            Group("Laptop connection") {
                Text(
                    "The address serve.bat printed when it started, like 192.168.1.40:8765. " +
                        "Over Tailscale, use the tailnet address. A full URL to a synced events.json works too.",
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.onSurfaceVariant,
                )
                Spacer(Modifier.height(14.dp))
                Field(url, { url = it }, "Server address", "192.168.1.40:8765", KeyboardType.Uri)
                Spacer(Modifier.height(10.dp))
                Field(token, { token = it }, "Token", "from server.token in config.yaml", KeyboardType.Text)
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = { onSave(url, token) },
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape = CircleShape,
                    colors = ButtonDefaults.buttonColors(containerColor = colors.primary, contentColor = colors.onPrimary),
                ) {
                    Text("Save and reconnect", style = MaterialTheme.typography.labelLarge)
                }

                val status = when {
                    state.error != null -> state.error to colors.error
                    state.feed != null -> "Connected. ${state.feed.events.size} event(s) in the feed." to colors.onSurfaceVariant
                    else -> null
                }
                status?.let { (text, color) ->
                    Spacer(Modifier.height(10.dp))
                    Text(text, style = MaterialTheme.typography.bodySmall, color = color)
                }
            }

            Group("Alerts") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Notify me about new finds", style = MaterialTheme.typography.bodyLarge, color = colors.onSurface)
                        Spacer(Modifier.height(2.dp))
                        Text(
                            "Checks a few times a day. Club events are posted days ahead, so that's plenty of warning.",
                            style = MaterialTheme.typography.bodySmall,
                            color = colors.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.padding(start = 12.dp))
                    Switch(checked = state.settings.notificationsEnabled, onCheckedChange = onToggleNotifications)
                }
            }

            Group("Appearance") {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    listOf(
                        ThemeMode.System to "Match phone",
                        ThemeMode.Light to "Light",
                        ThemeMode.Dark to "Dark",
                    ).forEach { (mode, label) ->
                        Pill(
                            label,
                            selected = state.settings.themeMode == mode,
                            onClick = { onThemeMode(mode) },
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            }

            Group("How sure is sure enough") {
                Text(
                    if (confidence <= 0f) "Showing everything the laptop sends."
                    else "Hiding anything below ${(confidence * 100).roundToInt()}% confidence.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = colors.onSurface,
                )
                Slider(
                    value = confidence,
                    onValueChange = { confidence = it },
                    onValueChangeFinished = { onMinConfidence(confidence) },
                    valueRange = 0f..0.95f,
                    steps = 18,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "The laptop applies its own threshold first. This hides more on top, without a rebuild.",
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}

/** A titled white card, like the grouped sections in the reference design. */
@Composable
private fun Group(title: String, content: @Composable ColumnScope.() -> Unit) {
    val colors = MaterialTheme.colorScheme
    Text(
        title,
        style = MaterialTheme.typography.titleSmall,
        color = colors.onSurfaceVariant,
        modifier = Modifier.padding(start = 4.dp, top = 18.dp, bottom = 8.dp),
    )
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(colors.surface)
            .padding(16.dp),
        content = content,
    )
}

@Composable
private fun Field(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    placeholder: String,
    keyboard: KeyboardType,
) {
    val colors = MaterialTheme.colorScheme
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        placeholder = { Text(placeholder) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        shape = RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = colors.surface,
            unfocusedContainerColor = colors.background,
            focusedBorderColor = colors.primary,
            unfocusedBorderColor = colors.outline,
            focusedLabelColor = colors.primary,
            cursorColor = colors.primary,
        ),
        modifier = Modifier.fillMaxWidth(),
    )
}
