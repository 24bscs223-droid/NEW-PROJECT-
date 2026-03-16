package com.proximitylock;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.AdvertiseCallback;
import android.bluetooth.le.AdvertiseData;
import android.bluetooth.le.AdvertiseSettings;
import android.bluetooth.le.BluetoothLeAdvertiser;
import android.content.Context;
import android.content.Intent;
import android.os.IBinder;
import android.os.ParcelUuid;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import java.util.UUID;

/**
 * Foreground service that continuously advertises a BLE beacon.
 *
 * The laptop daemon scans for this beacon and uses the received signal
 * strength (RSSI) to estimate whether the phone is within ~5 m.
 *
 * Beacon details
 * --------------
 *  Local name : "ProximityLock"  (configurable via {@link #BEACON_NAME})
 *  Service UUID: {@link #SERVICE_UUID}  (128-bit, custom)
 */
public class BluetoothBeaconService extends Service {

    private static final String TAG = "BLEBeaconService";

    // ── Beacon identity ────────────────────────────────────────────────────
    /** BLE local name broadcast in every advertisement packet. */
    public static final String BEACON_NAME = "ProximityLock";

    /**
     * Custom 128-bit UUID that uniquely identifies this app's beacon.
     * The laptop Python daemon filters advertisements by this UUID.
     */
    public static final UUID SERVICE_UUID =
        UUID.fromString("12345678-1234-5678-1234-56789abcdef0");

    // ── Intent actions ─────────────────────────────────────────────────────
    public static final String ACTION_START = "com.proximitylock.START_BEACON";
    public static final String ACTION_STOP  = "com.proximitylock.STOP_BEACON";

    // ── Notification ───────────────────────────────────────────────────────
    private static final String CHANNEL_ID   = "proximity_lock_channel";
    private static final int    NOTIF_ID     = 1001;

    // ── State ──────────────────────────────────────────────────────────────
    private static volatile boolean sRunning = false;

    private BluetoothLeAdvertiser advertiser;
    private AdvertiseCallback     advertiseCallback;

    // -----------------------------------------------------------------------
    // Service lifecycle
    // -----------------------------------------------------------------------

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_STICKY;

        String action = intent.getAction();
        if (ACTION_START.equals(action)) {
            startForeground(NOTIF_ID, buildNotification());
            startAdvertising();
        } else if (ACTION_STOP.equals(action)) {
            stopAdvertising();
            stopForeground(true);
            stopSelf();
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        stopAdvertising();
        sRunning = false;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null; // Not a bound service
    }

    // -----------------------------------------------------------------------
    // Public accessor (used by MainActivity to check state)
    // -----------------------------------------------------------------------

    /** Returns {@code true} while the beacon is actively advertising. */
    public static boolean isRunning() {
        return sRunning;
    }

    // -----------------------------------------------------------------------
    // BLE advertising
    // -----------------------------------------------------------------------

    private void startAdvertising() {
        BluetoothManager bm =
            (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        if (bm == null) {
            Log.e(TAG, "No BluetoothManager – cannot advertise.");
            return;
        }

        BluetoothAdapter adapter = bm.getAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            Log.e(TAG, "Bluetooth is off – cannot advertise.");
            return;
        }

        // Set the local BLE device name so scanners see "ProximityLock".
        adapter.setName(BEACON_NAME);

        advertiser = adapter.getBluetoothLeAdvertiser();
        if (advertiser == null) {
            Log.e(TAG, "Device does not support BLE advertising.");
            return;
        }

        AdvertiseSettings settings = new AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_POWER)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM)
            .setConnectable(false)
            .setTimeout(0)          // advertise indefinitely
            .build();

        AdvertiseData data = new AdvertiseData.Builder()
            .setIncludeDeviceName(true)
            .addServiceUuid(new ParcelUuid(SERVICE_UUID))
            .build();

        advertiseCallback = new AdvertiseCallback() {
            @Override
            public void onStartSuccess(AdvertiseSettings settingsInEffect) {
                Log.i(TAG, "BLE advertising started: " + BEACON_NAME);
                sRunning = true;
            }

            @Override
            public void onStartFailure(int errorCode) {
                Log.e(TAG, "BLE advertising failed: error " + errorCode);
                sRunning = false;
            }
        };

        advertiser.startAdvertising(settings, data, advertiseCallback);
    }

    private void stopAdvertising() {
        if (advertiser != null && advertiseCallback != null) {
            try {
                advertiser.stopAdvertising(advertiseCallback);
                Log.i(TAG, "BLE advertising stopped.");
            } catch (Exception e) {
                Log.w(TAG, "Error stopping advertising: " + e.getMessage());
            }
        }
        sRunning = false;
    }

    // -----------------------------------------------------------------------
    // Notification helpers
    // -----------------------------------------------------------------------

    private void createNotificationChannel() {
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Proximity Lock Beacon",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Running in the background to keep the BLE beacon active.");
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            nm.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification() {
        Intent openApp = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
            this, 0, openApp,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("ProximityLock Active")
            .setContentText("Broadcasting BLE beacon for screen lock/unlock.")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentIntent(pi)
            .setOngoing(true)
            .build();
    }
}
