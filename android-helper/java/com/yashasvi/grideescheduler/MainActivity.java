package com.yashasvi.grideescheduler;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private TextView status;
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(48, 72, 48, 48);
        box.setGravity(Gravity.CENTER_HORIZONTAL);
        TextView title = new TextView(this);
        title.setText("Gridee Scheduler"); title.setTextSize(26f); box.addView(title, row());
        TextView note = new TextView(this);
        note.setText("One-shot Android alarm using the normal Gridee UI. Enable accessibility once. A secure PIN cannot be bypassed.");
        note.setTextSize(16f); note.setPadding(0, 32, 0, 32); box.addView(note, row());
        status = new TextView(this); status.setTextSize(15f); box.addView(status, row());
        Button settings = new Button(this); settings.setText("Enable accessibility service");
        settings.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        box.addView(settings, row());
        Button cancel = new Button(this); cancel.setText("Cancel scheduled booking");
        cancel.setOnClickListener(v -> { Scheduler.cancel(this); refresh(); }); box.addView(cancel, row());
        setContentView(box);
    }
    private LinearLayout.LayoutParams row() { return new LinearLayout.LayoutParams(-1, -2); }
    private void refresh() { status.setText(Scheduler.status(this)); }
    @Override protected void onResume() { super.onResume(); refresh(); }
}

