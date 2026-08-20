package com.yashasvi.grideescheduler;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import java.text.DateFormat;
import java.util.Date;
import java.util.Locale;

final class Scheduler {
    static final String PREFS = "schedule";
    static final String GRIdEE_PACKAGE = "com.gridee.parking";
    private static final int REQUEST_CODE = 4105;

    private Scheduler() {}

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static PendingIntent operation(Context context) {
        Intent intent = new Intent(context, AlarmReceiver.class)
                .setAction("com.yashasvi.grideescheduler.FIRE");
        return PendingIntent.getBroadcast(context, REQUEST_CODE, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void schedule(Context context, long triggerAt) {
        AlarmManager manager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        PendingIntent pending = operation(context);
        if (Build.VERSION.SDK_INT >= 31 && !manager.canScheduleExactAlarms()) {
            manager.setAlarmClock(new AlarmManager.AlarmClockInfo(triggerAt, pending), pending);
        } else {
            manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pending);
        }
        prefs(context).edit().putLong("triggerAt", triggerAt).putBoolean("armed", true)
                .putString("status", "scheduled").apply();
    }

    static void cancel(Context context) {
        ((AlarmManager) context.getSystemService(Context.ALARM_SERVICE)).cancel(operation(context));
        prefs(context).edit().putBoolean("armed", false).putString("status", "cancelled").apply();
    }

    static String status(Context context) {
        SharedPreferences p = prefs(context);
        long trigger = p.getLong("triggerAt", 0L);
        String when = trigger == 0L ? "none" : DateFormat.getDateTimeInstance().format(new Date(trigger));
        return String.format(Locale.US,
                "armed=%s; status=%s; trigger=%s; venue=%s; window=%s-%s; execute=%s",
                p.getBoolean("armed", false), p.getString("status", "not configured"), when,
                p.getString("venue", "Tech Park Avenue"), p.getString("start", "08:00"),
                p.getString("end", "17:00"), p.getBoolean("execute", false));
    }
}

