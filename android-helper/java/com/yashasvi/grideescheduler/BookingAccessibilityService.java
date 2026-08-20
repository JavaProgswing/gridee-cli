package com.yashasvi.grideescheduler;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class BookingAccessibilityService extends AccessibilityService {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private long lastActionAt = 0L;
    private long driveUntil = 0L;
    private final Runnable driveAgain = new Runnable() {
        @Override public void run() {
            drive();
            if (isArmed() && System.currentTimeMillis() < driveUntil) handler.postDelayed(this, 900L);
        }
    };

    @Override protected void onServiceConnected() {
        AccessibilityServiceInfo info = getServiceInfo();
        info.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        setServiceInfo(info);
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        if (!isArmed()) return;
        if (driveUntil == 0L) driveUntil = System.currentTimeMillis() + 180000L;
        handler.removeCallbacks(driveAgain);
        handler.postDelayed(driveAgain, 250L);
    }

    @Override public void onInterrupt() {}

    private boolean isArmed() { return Scheduler.prefs(this).getBoolean("armed", false); }

    private void drive() {
        if (!isArmed() || System.currentTimeMillis() - lastActionAt < 650L) return;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null || !Scheduler.GRIdEE_PACKAGE.contentEquals(root.getPackageName())) return;

        AccessibilityNodeInfo success = byText(root, "booking confirmed|booking successful|your spot is reserved");
        if (success != null) {
            finish("booking confirmed");
            return;
        }
        AccessibilityNodeInfo failure = byText(root, "booking failed|spot unavailable|insufficient balance|already booked");
        if (failure != null) {
            finish("failed: " + text(failure));
            return;
        }

        SharedPreferences prefs = Scheduler.prefs(this);
        String stage = prefs.getString("stage", "home");
        if ("start_picker".equals(stage) || "end_picker".equals(stage)) {
            if (fillTimePicker(root, "start_picker".equals(stage) ? prefs.getString("start", "08:00")
                    : prefs.getString("end", "17:00"))) {
                prefs.edit().putString("stage", "sheet").apply();
            }
            return;
        }

        AccessibilityNodeInfo start = byId(root, "tvStartTime", "tv_start_time");
        AccessibilityNodeInfo end = byId(root, "tvEndTime", "tv_end_time");
        if (start != null && end != null) {
            String wantedStart = prefs.getString("start", "08:00");
            String wantedEnd = prefs.getString("end", "17:00");
            if (!sameTime(text(start), wantedStart)) {
                AccessibilityNodeInfo card = byId(root, "cardStartTime");
                if (click(card == null ? start : card)) {
                    prefs.edit().putString("stage", "start_picker").putString("status", "setting start time").apply();
                }
                return;
            }
            if (!sameTime(text(end), wantedEnd)) {
                AccessibilityNodeInfo card = byId(root, "cardEndTime");
                if (click(card == null ? end : card)) {
                    prefs.edit().putString("stage", "end_picker").putString("status", "setting end time").apply();
                }
                return;
            }
            AccessibilityNodeInfo confirm = byId(root, "btnConfirmContainer", "btnConfirm", "confirm_button");
            if (confirm == null) confirm = byText(root, "confirm booking|book now|reserve");
            if (confirm != null) {
                if (!prefs.getBoolean("execute", false)) {
                    finish("dry run ready; confirmation not pressed");
                } else if (click(confirm)) {
                    prefs.edit().putString("stage", "submitted").putString("status", "submitted; awaiting result").apply();
                }
            }
            return;
        }

        if (!"submitted".equals(stage)) chooseVenue(root, prefs);
    }

    private void chooseVenue(AccessibilityNodeInfo root, SharedPreferences prefs) {
        List<AccessibilityNodeInfo> names = byIdAll(root, "tv_spot_name");
        if (names.isEmpty()) return;
        String wanted = prefs.getString("venue", "Tech Park Avenue");
        float threshold = prefs.getFloat("threshold", 0.35f);
        AccessibilityNodeInfo bestAction = null;
        String bestName = null;
        double bestScore = -1.0;
        int bestAvailable = -1;
        for (AccessibilityNodeInfo nameNode : names) {
            String candidate = text(nameNode);
            AccessibilityNodeInfo container = ancestorWithText(nameNode, "park", 6);
            if (container == null) continue;
            AccessibilityNodeInfo action = byText(container, "^park$");
            int available = availability(container);
            if (available == 0) continue;
            double score = similarity(wanted, candidate);
            if (score > bestScore || (score == bestScore && available > bestAvailable)) {
                bestScore = score; bestAvailable = available; bestAction = action; bestName = candidate;
            }
        }
        if (bestAction == null || bestScore < threshold) {
            prefs.edit().putString("status", "no acceptable available venue found").apply();
            return;
        }
        if (click(bestAction)) {
            prefs.edit().putString("stage", "sheet").putString("selectedVenue", bestName)
                    .putString("status", "selected " + bestName).apply();
        }
    }

    private boolean fillTimePicker(AccessibilityNodeInfo root, String hhmm) {
        AccessibilityNodeInfo ok = byId(root, "material_timepicker_ok_button");
        if (ok == null) ok = byText(root, "^ok$");
        if (ok == null) return false;
        String[] parts = hhmm.split(":");
        int hour24 = Integer.parseInt(parts[0]);
        int minute = Integer.parseInt(parts[1]);
        int hour12 = hour24 % 12; if (hour12 == 0) hour12 = 12;
        List<AccessibilityNodeInfo> edits = byClass(root, "android.widget.EditText");
        if (edits.size() < 2) return false;
        setText(edits.get(0), String.valueOf(hour12));
        setText(edits.get(1), String.format(Locale.US, "%02d", minute));
        AccessibilityNodeInfo period = byText(root, hour24 >= 12 ? "^pm$" : "^am$");
        if (period != null) click(period);
        return click(ok);
    }

    private void finish(String status) {
        Scheduler.prefs(this).edit().putBoolean("armed", false).putString("stage", "done")
                .putString("status", status).putLong("completedAt", System.currentTimeMillis()).apply();
        handler.removeCallbacks(driveAgain);
    }

    private boolean click(AccessibilityNodeInfo node) {
        if (node == null) return false;
        AccessibilityNodeInfo current = node;
        for (int i = 0; i < 5 && current != null; i++) {
            if (current.isClickable() && current.isEnabled()) {
                lastActionAt = System.currentTimeMillis();
                return current.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            }
            current = current.getParent();
        }
        return false;
    }

    private static void setText(AccessibilityNodeInfo node, String value) {
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value);
        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
    }

    private static String text(AccessibilityNodeInfo node) {
        if (node == null) return "";
        CharSequence value = node.getText();
        if (value == null || value.length() == 0) value = node.getContentDescription();
        return value == null ? "" : value.toString();
    }

    private static AccessibilityNodeInfo byId(AccessibilityNodeInfo root, String... shortIds) {
        for (String id : shortIds) {
            List<AccessibilityNodeInfo> found = root.findAccessibilityNodeInfosByViewId(Scheduler.GRIdEE_PACKAGE + ":id/" + id);
            if (found != null && !found.isEmpty()) return found.get(0);
        }
        return null;
    }

    private static List<AccessibilityNodeInfo> byIdAll(AccessibilityNodeInfo root, String shortId) {
        List<AccessibilityNodeInfo> found = root.findAccessibilityNodeInfosByViewId(Scheduler.GRIdEE_PACKAGE + ":id/" + shortId);
        return found == null ? new ArrayList<>() : found;
    }

    private static AccessibilityNodeInfo byText(AccessibilityNodeInfo root, String regex) {
        Pattern pattern = Pattern.compile(regex, Pattern.CASE_INSENSITIVE);
        List<AccessibilityNodeInfo> all = new ArrayList<>(); collect(root, all);
        for (AccessibilityNodeInfo node : all) if (pattern.matcher(text(node).trim()).find()) return node;
        return null;
    }

    private static List<AccessibilityNodeInfo> byClass(AccessibilityNodeInfo root, String className) {
        List<AccessibilityNodeInfo> all = new ArrayList<>(); collect(root, all);
        List<AccessibilityNodeInfo> result = new ArrayList<>();
        for (AccessibilityNodeInfo node : all) if (className.contentEquals(node.getClassName())) result.add(node);
        return result;
    }

    private static void collect(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> out) {
        if (node == null) return;
        out.add(node);
        for (int i = 0; i < node.getChildCount(); i++) collect(node.getChild(i), out);
    }

    private static AccessibilityNodeInfo ancestorWithText(AccessibilityNodeInfo node, String regex, int levels) {
        AccessibilityNodeInfo current = node;
        for (int i = 0; i < levels && current != null; i++) {
            if (byText(current, regex) != null) return current;
            current = current.getParent();
        }
        return null;
    }

    private static int availability(AccessibilityNodeInfo container) {
        List<AccessibilityNodeInfo> all = new ArrayList<>(); collect(container, all);
        Pattern pattern = Pattern.compile("(\\d+)\\s+available", Pattern.CASE_INSENSITIVE);
        for (AccessibilityNodeInfo node : all) {
            Matcher match = pattern.matcher(text(node));
            if (match.find()) return Integer.parseInt(match.group(1));
        }
        return -1;
    }

    private static boolean sameTime(String displayed, String wanted24) {
        String[] parts = wanted24.split(":");
        int hour = Integer.parseInt(parts[0]);
        int minute = Integer.parseInt(parts[1]);
        String wanted = String.format(Locale.US, "%d:%02d %s", hour % 12 == 0 ? 12 : hour % 12,
                minute, hour >= 12 ? "pm" : "am");
        return displayed.trim().toLowerCase(Locale.US).replaceAll("\\s+", " ").equals(wanted);
    }

    private static double similarity(String left, String right) {
        String a = normalize(left), b = normalize(right);
        if (a.equals(b)) return 1.0;
        Set<String> x = new HashSet<>(), y = new HashSet<>();
        for (String s : a.split(" ")) if (!s.isEmpty()) x.add(s);
        for (String s : b.split(" ")) if (!s.isEmpty()) y.add(s);
        Set<String> overlap = new HashSet<>(x); overlap.retainAll(y);
        double token = x.isEmpty() && y.isEmpty() ? 0.0 : 2.0 * overlap.size() / (x.size() + y.size());
        int distance = levenshtein(a, b);
        double edit = 1.0 - (double) distance / Math.max(a.length(), b.length());
        return Math.max(token, edit);
    }

    private static String normalize(String value) {
        String n = value.toLowerCase(Locale.US).replaceAll("[^a-z0-9]+", " ").trim();
        n = n.replaceAll("\\btp\\b", "tech park");
        return n.replaceAll("\\s+", " ");
    }

    private static int levenshtein(String a, String b) {
        int[] prev = new int[b.length() + 1], next = new int[b.length() + 1];
        for (int j = 0; j <= b.length(); j++) prev[j] = j;
        for (int i = 1; i <= a.length(); i++) {
            next[0] = i;
            for (int j = 1; j <= b.length(); j++) {
                int cost = a.charAt(i - 1) == b.charAt(j - 1) ? 0 : 1;
                next[j] = Math.min(Math.min(next[j - 1] + 1, prev[j] + 1), prev[j - 1] + cost);
            }
            int[] swap = prev; prev = next; next = swap;
        }
        return prev[b.length()];
    }
}

