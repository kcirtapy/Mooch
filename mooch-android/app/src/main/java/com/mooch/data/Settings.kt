package com.mooch.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "mooch_settings")

/** Follow the phone's setting, or force one. */
enum class ThemeMode { System, Light, Dark }

data class Settings(
    val serverUrl: String = "",
    val token: String = "",
    val notificationsEnabled: Boolean = true,
    val minConfidence: Float = 0f,
    val savedIds: Set<String> = emptySet(),
    val themeMode: ThemeMode = ThemeMode.System,
) {
    val isConfigured: Boolean get() = serverUrl.isNotBlank()

    /** Accepts "laptop.local:8765" or a full URL, with or without the path. */
    fun feedUrl(): String? {
        if (serverUrl.isBlank()) return null
        var base = serverUrl.trim().trimEnd('/')
        if (!base.startsWith("http://") && !base.startsWith("https://")) base = "http://$base"
        return if (base.endsWith(".json") || base.contains("/api/")) base else "$base/api/events.json"
    }
}

class SettingsRepository(private val context: Context) {

    private object Keys {
        val URL = stringPreferencesKey("server_url")
        val TOKEN = stringPreferencesKey("token")
        val NOTIFY = booleanPreferencesKey("notifications")
        val MIN_CONF = floatPreferencesKey("min_confidence")
        val NOTIFIED = stringSetPreferencesKey("notified_ids")
        val CACHE = stringPreferencesKey("cached_feed")
        val SAVED = stringSetPreferencesKey("saved_ids")
        val THEME = stringPreferencesKey("theme_mode")
    }

    val settings: Flow<Settings> = context.dataStore.data.map { p ->
        Settings(
            serverUrl = p[Keys.URL] ?: "",
            token = p[Keys.TOKEN] ?: "",
            notificationsEnabled = p[Keys.NOTIFY] ?: true,
            minConfidence = p[Keys.MIN_CONF] ?: 0f,
            savedIds = p[Keys.SAVED] ?: emptySet(),
            themeMode = ThemeMode.entries.firstOrNull { it.name == p[Keys.THEME] } ?: ThemeMode.System,
        )
    }

    suspend fun current(): Settings = settings.first()

    suspend fun save(serverUrl: String, token: String) {
        context.dataStore.edit {
            it[Keys.URL] = serverUrl.trim()
            it[Keys.TOKEN] = token.trim()
        }
    }

    suspend fun setNotifications(enabled: Boolean) {
        context.dataStore.edit { it[Keys.NOTIFY] = enabled }
    }

    suspend fun setMinConfidence(value: Float) {
        context.dataStore.edit { it[Keys.MIN_CONF] = value }
    }

    suspend fun setThemeMode(mode: ThemeMode) {
        context.dataStore.edit { it[Keys.THEME] = mode.name }
    }

    /**
     * Bookmark or un-bookmark an event. Saved events survive restarts.
     *
     * [ids] is the event's own id, then those of any duplicates merged into it.
     * The event counts as saved if any of them is, so un-saving clears them all.
     */
    suspend fun toggleSaved(ids: List<String>) {
        if (ids.isEmpty()) return
        context.dataStore.edit { prefs ->
            val current = prefs[Keys.SAVED] ?: emptySet()
            prefs[Keys.SAVED] =
                if (ids.any { it in current }) current - ids.toSet() else current + ids.first()
        }
    }

    // -- offline cache -----------------------------------------------------

    suspend fun cacheFeed(json: String) {
        context.dataStore.edit { it[Keys.CACHE] = json }
    }

    suspend fun cachedFeed(): String? = context.dataStore.data.first()[Keys.CACHE]

    // -- notification bookkeeping -----------------------------------------

    suspend fun notifiedIds(): Set<String> =
        context.dataStore.data.first()[Keys.NOTIFIED] ?: emptySet()

    /** Remembers what we've already alerted on, capped so it can't grow forever. */
    suspend fun markNotified(ids: Set<String>) {
        context.dataStore.edit { prefs ->
            val merged = (prefs[Keys.NOTIFIED] ?: emptySet()) + ids
            prefs[Keys.NOTIFIED] =
                if (merged.size > 400) merged.toList().takeLast(400).toSet() else merged
        }
    }
}
