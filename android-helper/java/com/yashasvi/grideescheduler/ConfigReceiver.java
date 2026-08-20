package com.yashasvi.grideescheduler;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

public final class ConfigReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if ("com.yashasvi.grideescheduler.CANCEL".equals(action)) {
            Scheduler.cancel(context);
            setResultData(Scheduler.status(context));
            return;
        }
        if ("com.yashasvi.grideescheduler.STATUS".equals(action)) {
            setResultData(Scheduler.status(context));
            return;
        }
        if (!"com.yashasvi.grideescheduler.CONFIGURE".equals(action)) return;
        long trigger = intent.getLongExtra("triggerAt", 0L);
        if (trigger <= 0L) {
            setResultCode(2);
            setResultData("missing triggerAt epoch milliseconds");
            return;
        }
        SharedPreferences.Editor e = Scheduler.prefs(context).edit();
        e.putString("venue", value(intent, "venue", "Tech Park Avenue"));
        e.putString("start", value(intent, "start", "08:00"));
        e.putString("end", value(intent, "end", "17:00"));
        e.putString("date", value(intent, "date", ""));
        e.putBoolean("execute", intent.getBooleanExtra("execute", false));
        e.putFloat("threshold", intent.getFloatExtra("threshold", 0.35f));
        e.putLong("configuredAt", System.currentTimeMillis());
        e.putString("status", "configured");
        e.apply();
        Scheduler.schedule(context, trigger);
        setResultData(Scheduler.status(context));
    }

    private static String value(Intent intent, String key, String fallback) {
        String value = intent.getStringExtra(key);
        return value == null || value.length() == 0 ? fallback : value;
    }
}

