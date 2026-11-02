package com.mooch.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.mooch.MainActivity
import com.mooch.R
import com.mooch.data.EventRepository
import com.mooch.data.Fmt
import com.mooch.data.MoochEvent
import com.mooch.data.SettingsRepository
import java.time.ZoneId
import java.util.concurrent.TimeUnit

private const val CHANNEL_ID = "mooch_finds"
private const val WORK_NAME = "mooch_sync"

object SyncScheduler {

    /**
     * Clubs register events days ahead, so there is nothing to gain from
     * polling aggressively — three hours gives eight checks a day and costs
     * almost no battery. It is also comfortably above WorkManager's 15-minute
     * floor, so Doze deferring a run by a few minutes is irrelevant.
     *
     * KEEP means an existing schedule isn't torn down and restarted every time
     * the app launches. To pick up a changed interval, toggle notifications off
     * and back on in Settings.
     */
    private const val INTERVAL_HOURS = 3L

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<SyncWorker>(INTERVAL_HOURS, TimeUnit.HOURS)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
    }
}

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val settings = SettingsRepository(applicationContext).current()
        if (!settings.isConfigured || !settings.notificationsEnabled) return Result.success()

        val repo = EventRepository(applicationContext)
        val (feed, freshIds) = repo.refreshForSync() ?: return Result.retry()

        if (freshIds.isEmpty()) return Result.success()

        val zone = runCatching { ZoneId.of(feed.timezone) }.getOrDefault(ZoneId.systemDefault())
        val fresh = feed.events.filter { it.id in freshIds }.sortedBy { it.start }

        Notifications.notifyFinds(applicationContext, fresh, zone)
        repo.markNotified(freshIds)
        return Result.success()
    }
}

object Notifications {

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Free food",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "New free food found on campus"
            enableVibration(true)
        }
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun canPost(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    fun notifyFinds(context: Context, events: List<MoochEvent>, zone: ZoneId) {
        if (events.isEmpty() || !canPost(context)) return
        ensureChannel(context)

        val intent = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE,
        )

        val top = events.first()
        val title = buildString {
            append(top.food?.replaceFirstChar { it.uppercase() } ?: "Free food")
            append(" ")
            append(Fmt.relative(top.start))
        }
        val line = listOfNotNull(top.title, top.location).joinToString(" · ")

        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(line)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_EVENT)
            .setAutoCancel(true)
            .setContentIntent(intent)

        if (events.size > 1) {
            val style = NotificationCompat.InboxStyle().setBigContentTitle("${events.size} new finds")
            events.take(5).forEach { event ->
                style.addLine(
                    "${Fmt.time(event.start, zone)}  ${event.food ?: "food"} — ${event.title}"
                )
            }
            builder.setStyle(style)
        } else {
            builder.setStyle(NotificationCompat.BigTextStyle().bigText(top.metaLine()))
        }

        runCatching {
            NotificationManagerCompat.from(context).notify(top.id.hashCode(), builder.build())
        }
    }
}
