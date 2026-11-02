package com.mooch.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp

/** The app's two tabs. The round button between them is an action, not a tab. */
enum class Tab { Home, Settings }

/**
 * Shared by every screen, so Home, refresh and Settings are always in reach.
 * The current tab is drawn in red with a small bar under it.
 */
@Composable
fun MoochBottomBar(
    current: Tab,
    loading: Boolean,
    onHome: () -> Unit,
    onRefresh: () -> Unit,
    onSettings: () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    Surface(color = colors.surface, shadowElevation = 16.dp) {
        Row(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .height(72.dp)
                .padding(horizontal = 44.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            NavItem(
                icon = if (current == Tab.Home) Icons.Filled.Home else Icons.Outlined.Home,
                label = "Home",
                selected = current == Tab.Home,
                onClick = onHome,
            )

            // Where the reference app has its big "+": check for new food.
            Box(
                Modifier
                    .size(56.dp)
                    .clip(CircleShape)
                    .background(colors.inverseSurface)
                    .clickable(enabled = !loading, onClick = onRefresh),
                contentAlignment = Alignment.Center,
            ) {
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(22.dp),
                        color = colors.inverseOnSurface,
                        strokeWidth = 2.5.dp,
                    )
                } else {
                    Icon(
                        Icons.Outlined.Refresh,
                        contentDescription = "Check for new food",
                        tint = colors.inverseOnSurface,
                        modifier = Modifier.size(26.dp),
                    )
                }
            }

            NavItem(
                icon = if (current == Tab.Settings) Icons.Filled.Settings else Icons.Outlined.Settings,
                label = "Settings",
                selected = current == Tab.Settings,
                onClick = onSettings,
            )
        }
    }
}

@Composable
private fun NavItem(icon: ImageVector, label: String, selected: Boolean, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        IconButton(onClick = onClick) {
            Icon(
                icon,
                contentDescription = label,
                tint = if (selected) colors.primary else colors.onSurfaceVariant,
                modifier = Modifier.size(27.dp),
            )
        }
        Box(
            Modifier
                .width(20.dp)
                .height(3.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(if (selected) colors.primary else Color.Transparent),
        )
    }
}
