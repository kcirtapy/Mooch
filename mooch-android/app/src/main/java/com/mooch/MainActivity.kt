package com.mooch

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mooch.data.ThemeMode
import com.mooch.ui.EventListScreen
import com.mooch.ui.FeedTab
import com.mooch.ui.MainViewModel
import com.mooch.ui.MoochBottomBar
import com.mooch.ui.SettingsScreen
import com.mooch.ui.Tab
import com.mooch.ui.theme.MoochTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val vm: MainViewModel = viewModel()
            val state by vm.state.collectAsStateWithLifecycle()
            val dark = when (state.settings.themeMode) {
                ThemeMode.System -> isSystemInDarkTheme()
                ThemeMode.Light -> false
                ThemeMode.Dark -> true
            }
            MoochTheme(darkTheme = dark) {
                MoochRoot(vm)
            }
        }
    }
}

@Composable
private fun MoochRoot(vm: MainViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()
    // rememberSaveable so the current tab survives rotation. Enums store fine in a Bundle.
    var tab by rememberSaveable { mutableStateOf(Tab.Home) }
    val scope = rememberCoroutineScope()

    // Hoisted here so the feed keeps its scroll position while you're in Settings.
    val listState = rememberLazyListState()

    // Asked once on first launch; the app works fine if it's declined, the
    // list just won't push anything.
    val permission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* either way, carry on */ }

    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    // Settings is a tab, not a page on top of Home, so there's no back arrow.
    // The phone's own back gesture still returns Home rather than closing the app.
    BackHandler(enabled = tab == Tab.Settings) { tab = Tab.Home }

    val bottomBar: @Composable () -> Unit = {
        MoochBottomBar(
            current = tab,
            loading = state.loading,
            onHome = {
                if (tab == Tab.Home) {
                    // Already home: tapping again jumps back to the top of all events.
                    vm.setTab(FeedTab.All)
                    scope.launch { listState.animateScrollToItem(0) }
                } else {
                    tab = Tab.Home
                }
            },
            onRefresh = vm::refresh,
            onSettings = { tab = Tab.Settings },
        )
    }

    when (tab) {
        Tab.Home -> EventListScreen(
            state = state,
            onRefresh = vm::refresh,
            onOpenSettings = { tab = Tab.Settings },
            onQuery = vm::setQuery,
            onTab = vm::setTab,
            onToggleSource = vm::toggleSource,
            onResetSources = vm::resetSources,
            onToggleSaved = vm::toggleSaved,
            listState = listState,
            bottomBar = bottomBar,
        )
        Tab.Settings -> SettingsScreen(
            state = state,
            onSave = { url, token -> vm.saveConnection(url, token) },
            onToggleNotifications = vm::setNotifications,
            onMinConfidence = vm::setMinConfidence,
            onThemeMode = vm::setThemeMode,
            bottomBar = bottomBar,
        )
    }
}
