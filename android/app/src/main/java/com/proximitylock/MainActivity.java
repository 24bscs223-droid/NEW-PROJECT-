package com.proximitylock;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import java.util.ArrayList;
import java.util.List;

/**
 * Main screen of the ProximityLock companion app.
 *
 * The user can start / stop the BLE beacon service from here.
 * The service advertises a custom UUID so the laptop daemon can detect the
 * phone's proximity by measuring the received signal strength (RSSI).
 */
public class MainActivity extends AppCompatActivity {

    private TextView statusText;
    private Button  toggleButton;

    private boolean serviceRunning = false;

    // -----------------------------------------------------------------------
    // Permission handling (Android 12+ requires BLUETOOTH_ADVERTISE)
    // -----------------------------------------------------------------------

    private final ActivityResultLauncher<String[]> permissionLauncher =
        registerForActivityResult(
            new ActivityResultContracts.RequestMultiplePermissions(),
            result -> {
                boolean allGranted = true;
                for (boolean granted : result.values()) {
                    if (!granted) {
                        allGranted = false;
                        break;
                    }
                }
                if (allGranted) {
                    startBeaconService();
                } else {
                    Toast.makeText(this,
                        "Bluetooth permissions are required for the proximity beacon.",
                        Toast.LENGTH_LONG).show();
                }
            }
        );

    // -----------------------------------------------------------------------
    // Activity lifecycle
    // -----------------------------------------------------------------------

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        statusText   = findViewById(R.id.status_text);
        toggleButton = findViewById(R.id.toggle_button);

        toggleButton.setOnClickListener(this::onToggleClicked);
        updateUI();
    }

    @Override
    protected void onResume() {
        super.onResume();
        serviceRunning = BluetoothBeaconService.isRunning();
        updateUI();
    }

    // -----------------------------------------------------------------------
    // UI helpers
    // -----------------------------------------------------------------------

    private void updateUI() {
        if (serviceRunning) {
            statusText.setText(R.string.status_advertising);
            toggleButton.setText(R.string.stop_beacon);
        } else {
            statusText.setText(R.string.status_stopped);
            toggleButton.setText(R.string.start_beacon);
        }
    }

    private void onToggleClicked(View v) {
        if (serviceRunning) {
            stopBeaconService();
        } else {
            requestPermissionsAndStart();
        }
    }

    // -----------------------------------------------------------------------
    // Bluetooth checks
    // -----------------------------------------------------------------------

    private boolean isBluetoothEnabled() {
        BluetoothManager bm = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        if (bm == null) return false;
        BluetoothAdapter adapter = bm.getAdapter();
        return adapter != null && adapter.isEnabled();
    }

    // -----------------------------------------------------------------------
    // Permission + service start
    // -----------------------------------------------------------------------

    private void requestPermissionsAndStart() {
        if (!isBluetoothEnabled()) {
            Toast.makeText(this, "Please turn on Bluetooth first.", Toast.LENGTH_SHORT).show();
            return;
        }

        List<String> needed = new ArrayList<>();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            // Android 12+
            if (ContextCompat.checkSelfPermission(this,
                    Manifest.permission.BLUETOOTH_ADVERTISE)
                    != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.BLUETOOTH_ADVERTISE);
            }
            if (ContextCompat.checkSelfPermission(this,
                    Manifest.permission.BLUETOOTH_CONNECT)
                    != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.BLUETOOTH_CONNECT);
            }
        } else {
            // Android 6–11
            if (ContextCompat.checkSelfPermission(this,
                    Manifest.permission.ACCESS_FINE_LOCATION)
                    != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.ACCESS_FINE_LOCATION);
            }
        }

        if (needed.isEmpty()) {
            startBeaconService();
        } else {
            permissionLauncher.launch(needed.toArray(new String[0]));
        }
    }

    private void startBeaconService() {
        Intent intent = new Intent(this, BluetoothBeaconService.class);
        intent.setAction(BluetoothBeaconService.ACTION_START);
        ContextCompat.startForegroundService(this, intent);
        serviceRunning = true;
        updateUI();
        Toast.makeText(this, "Proximity beacon started.", Toast.LENGTH_SHORT).show();
    }

    private void stopBeaconService() {
        Intent intent = new Intent(this, BluetoothBeaconService.class);
        intent.setAction(BluetoothBeaconService.ACTION_STOP);
        startService(intent);
        serviceRunning = false;
        updateUI();
        Toast.makeText(this, "Proximity beacon stopped.", Toast.LENGTH_SHORT).show();
    }
}
