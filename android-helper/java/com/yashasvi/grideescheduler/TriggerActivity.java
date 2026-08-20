package com.yashasvi.grideescheduler;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.Intent;
import android.os.Bundle;
import android.os.PowerManager;

public final class TriggerActivity extends Activity {
    private PowerManager.WakeLock lock;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        setShowWhenLocked(true);
        setTurnScreenOn(true);
        PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
        lock = power.newWakeLock(PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "GrideeScheduler:booking");
        lock.acquire(180000L);
        ((KeyguardManager) getSystemService(KEYGUARD_SERVICE)).requestDismissKeyguard(this, null);
        Scheduler.prefs(this).edit().putString("status", "launching Gridee").apply();
        Intent launch = getPackageManager().getLaunchIntentForPackage(Scheduler.GRIdEE_PACKAGE);
        if (launch == null) {
            Scheduler.prefs(this).edit().putString("status", "Gridee is not installed").apply();
            finish();
            return;
        }
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        startActivity(launch);
        getWindow().getDecorView().postDelayed(this::finish, 2500L);
    }

    @Override protected void onDestroy() {
        if (lock != null && lock.isHeld()) lock.release();
        super.onDestroy();
    }
}

