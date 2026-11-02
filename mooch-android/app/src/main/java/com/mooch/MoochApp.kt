package com.mooch

import android.app.Application
import com.mooch.work.Notifications
import com.mooch.work.SyncScheduler

class MoochApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Notifications.ensureChannel(this)
        // KEEP policy means this is a no-op if it's already scheduled.
        SyncScheduler.schedule(this)
    }
}
