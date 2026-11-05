package com.mooch.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mooch.data.EventRepository
import com.mooch.data.Feed
import com.mooch.data.FetchResult
import com.mooch.data.MoochEvent
import com.mooch.data.Settings
import com.mooch.data.SettingsRepository
import com.mooch.data.ThemeMode
import com.mooch.work.SyncScheduler
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class FeedTab { All, Saved }

/** Every source the laptop can report, in the order the filter sheet lists them. */
val ALL_SOURCES = listOf("jumbolife", "email", "instagram")

data class UiState(
    val feed: Feed? = null,
    val loading: Boolean = false,
    val error: String? = null,
    val stale: Boolean = false,
    val settings: Settings = Settings(),
    val query: String = "",
    val tab: FeedTab = FeedTab.All,
    val sources: Set<String> = ALL_SOURCES.toSet(),
) {
    val filtersActive: Boolean get() = sources.size < ALL_SOURCES.size

    /** Saved events still in the feed. A merged event counts once. */
    val savedCount: Int get() = feed?.events.orEmpty().count { it.isSavedIn(settings.savedIds) }

    /**
     * What the list shows once search, tab and source filters are applied. A
     * merged event matches through any of its listings: it stays visible with
     * JumboLife switched off if a club also posted it on Instagram.
     */
    fun visibleEvents(): List<MoochEvent> {
        val q = query.trim().lowercase()
        return feed?.events.orEmpty().filter { e ->
            (tab == FeedTab.All || e.isSavedIn(settings.savedIds)) &&
                e.allSources.any { it in sources || it !in ALL_SOURCES } &&
                (q.isEmpty() || (listOfNotNull(e.title, e.food, e.location, e.author) +
                    e.also.flatMap { listOfNotNull(it.author, it.title) })
                    .any { it.lowercase().contains(q) })
        }
    }
}

class MainViewModel(app: Application) : AndroidViewModel(app) {

    private val repo = EventRepository(app)
    private val settingsRepo = SettingsRepository(app)

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            settingsRepo.settings.collect { s ->
                _state.update { it.copy(settings = s) }
            }
        }
        viewModelScope.launch {
            // Show whatever we had before hitting the network, so the list
            // isn't empty for the first second on every launch.
            (repo.cached() as? FetchResult.Success)?.let { cached ->
                _state.update { prev -> prev.copy(feed = cached.feed, stale = true) }
            }
            refresh()
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            when (val result = repo.refresh()) {
                is FetchResult.Success -> _state.update {
                    it.copy(feed = result.feed, loading = false, error = null, stale = false)
                }
                is FetchResult.Failure -> _state.update {
                    it.copy(
                        feed = result.stale ?: it.feed,
                        loading = false,
                        error = result.message,
                        stale = true,
                    )
                }
            }
        }
    }

    // -- browsing --------------------------------------------------------------

    fun setQuery(q: String) = _state.update { it.copy(query = q) }

    fun setTab(tab: FeedTab) = _state.update { it.copy(tab = tab) }

    fun toggleSource(source: String) = _state.update {
        val next = if (source in it.sources) it.sources - source else it.sources + source
        // Never let every source be switched off; an empty feed looks broken.
        it.copy(sources = next.ifEmpty { it.sources })
    }

    fun resetSources() = _state.update { it.copy(sources = ALL_SOURCES.toSet()) }

    fun toggleSaved(id: String) {
        // A merged event may have been saved under one of its duplicates' ids.
        val ids = _state.value.feed?.events?.firstOrNull { it.id == id }?.allIds ?: listOf(id)
        viewModelScope.launch { settingsRepo.toggleSaved(ids) }
    }

    // -- settings --------------------------------------------------------------

    fun saveConnection(url: String, token: String, onDone: () -> Unit = {}) {
        viewModelScope.launch {
            settingsRepo.save(url, token)
            refresh()
            onDone()
        }
    }

    fun setNotifications(enabled: Boolean) {
        viewModelScope.launch {
            settingsRepo.setNotifications(enabled)
            val ctx = getApplication<Application>()
            if (enabled) SyncScheduler.schedule(ctx) else SyncScheduler.cancel(ctx)
        }
    }

    fun setThemeMode(mode: ThemeMode) {
        viewModelScope.launch { settingsRepo.setThemeMode(mode) }
    }

    fun setMinConfidence(value: Float) {
        viewModelScope.launch {
            settingsRepo.setMinConfidence(value)
            refresh()
        }
    }
}
