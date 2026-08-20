package com.yashasvi.grideescheduler;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

public final class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        SharedPreferences p = Scheduler.prefs(context);
        if (!p.getBoolean("armed", false)) return;
        long trigger = p.getLong("triggerAt", 0L);
        if (trigger > System.currentTimeMillis()) {
            Scheduler.schedule(context, trigger);
        } else {
            p.edit().putBoolean("armed", false).putString("status", "missed while powered off").apply();
        }
    }
}

