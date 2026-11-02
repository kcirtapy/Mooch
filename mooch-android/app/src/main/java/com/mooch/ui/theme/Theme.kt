package com.mooch.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat

// The canvas is the app icon's cream, cards are white, and the one accent is
// the apple's red. Dark mode keeps the same warmth: brown-black, not grey.
//
// Slot mapping, so screens can stay on MaterialTheme.colorScheme:
//   primary            accent red (pills, buttons, countdowns)
//   primaryContainer   pale red tint behind the food name on each card
//   inverseSurface     the dark round refresh button
//   tertiary(Container) the amber "not sure" badge

private val AppleRed = Color(0xFFEB4A43)
private val IconCream = Color(0xFFFDF6ED)   // the launcher icon's background

private val LightColors = lightColorScheme(
    primary = AppleRed,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFDE6E2),
    onPrimaryContainer = Color(0xFFCF3A33),
    background = IconCream,
    onBackground = Color(0xFF231F1B),
    surface = Color.White,
    onSurface = Color(0xFF231F1B),
    surfaceVariant = IconCream,
    onSurfaceVariant = Color(0xFF8C847A),
    outline = Color(0xFFEBE0D2),
    outlineVariant = Color(0xFFF3EADF),
    inverseSurface = Color(0xFF2B2622),
    inverseOnSurface = Color.White,
    tertiary = Color(0xFFA86A12),
    tertiaryContainer = Color(0xFFFFF0D6),
    error = Color(0xFFCF3A33),
    onError = Color.White,
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFFF6A62),
    onPrimary = Color(0xFF2B0B09),
    primaryContainer = Color(0xFF3D211D),
    onPrimaryContainer = Color(0xFFFF8F88),
    background = Color(0xFF16130F),
    onBackground = IconCream,
    surface = Color(0xFF221E1A),
    onSurface = IconCream,
    surfaceVariant = Color(0xFF2B2621),
    onSurfaceVariant = Color(0xFFA69C90),
    outline = Color(0xFF362F29),
    outlineVariant = Color(0xFF2B2621),
    // The round refresh button turns the icon's cream in the dark.
    inverseSurface = IconCream,
    inverseOnSurface = Color(0xFF231F1B),
    tertiary = Color(0xFFF0B45A),
    tertiaryContainer = Color(0xFF3B2D15),
    error = Color(0xFFFF6A62),
    onError = Color(0xFF2B0B09),
)

// One family, hierarchy carried by weight and size. For a rounder feel like the
// reference, drop a .ttf into res/font and swap FontFamily.Default below.
private val Sans = FontFamily.Default

private val MoochType = Typography(
    headlineSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 23.sp, lineHeight = 28.sp, letterSpacing = (-0.3).sp),
    titleLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 20.sp, lineHeight = 25.sp, letterSpacing = (-0.2).sp),
    titleMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 18.sp, lineHeight = 23.sp, letterSpacing = (-0.1).sp),
    titleSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 22.sp),
    bodyMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 19.sp),
    bodySmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Normal, fontSize = 13.sp, lineHeight = 17.sp),
    labelLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 13.sp, lineHeight = 17.sp),
    labelSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 16.sp),
)

@Composable
fun MoochTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colors = if (darkTheme) DarkColors else LightColors
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            val controller = WindowCompat.getInsetsController(window, view)
            controller.isAppearanceLightStatusBars = !darkTheme
            controller.isAppearanceLightNavigationBars = !darkTheme
        }
    }

    MaterialTheme(colorScheme = colors, typography = MoochType, content = content)
}
