package com.yashasvi.grideescheduler;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

public final class AlarmReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        SharedPreferences p = Scheduler.prefs(context);
        if (!p.getBoolean("armed", false)) return;
        long firedAt = System.currentTimeMillis();
        if (p.getBoolean("daily", false)) {
            Scheduler.schedule(context, Scheduler.nextDailyTrigger(p.getLong("triggerAt", firedAt)));
        }
        p.edit().putBoolean("running", true)
                .putBoolean("runExecute", p.getBoolean("execute", false)).putString("stage", "home")
                .putString("status", "alarm fired").putLong("firedAt", firedAt).apply();
        context.startActivity(new Intent(context, TriggerActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP));
    }
}

