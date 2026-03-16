package com.proximitylock;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

import androidx.core.content.ContextCompat;

/**
 * Starts the BLE beacon service automatically after the device reboots,
 * restoring proximity locking without any user interaction.
 */
public class BootReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || intent.getAction() == null) {
            return; // Guard against null or malformed intents
        }
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            Intent serviceIntent = new Intent(context, BluetoothBeaconService.class);
            serviceIntent.setAction(BluetoothBeaconService.ACTION_START);
            ContextCompat.startForegroundService(context, serviceIntent);
        }
    }
}
