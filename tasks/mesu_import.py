#!/usr/bin/env python3

import json
import plistlib
import random
import re
from pathlib import Path
import argparse
from datetime import datetime, timezone
import zoneinfo

import remotezip
import requests

from sort_os_files import sort_os_file
from update_links import update_links

parser = argparse.ArgumentParser()
parser.add_argument('-b', '--beta', action='store_true')
args = parser.parse_args()

SESSION = requests.session()

beta_asset_subfolders = {
    'AirPods': 'AirPods2022Seed'
}

asset_types = {
    'AirPods': {
        'A2032': 'com_apple_MobileAsset_MobileAccessoryUpdate_A2032_EA',
        'A2084': 'com_apple_MobileAsset_MobileAccessoryUpdate_A2084_EA',
        'A2096': 'com_apple_MobileAsset_MobileAccessoryUpdate_A2096_EA',
        'A2564': 'com_apple_MobileAsset_MobileAccessoryUpdate_A2564_EA',
        'A2618': 'com_apple_MobileAsset_UARP_A2618',
        'A2968': 'com_apple_MobileAsset_UARP_A2968',
        'A3048': 'com_apple_MobileAsset_UARP_A3048'
    },
    'AirTags': {
        'A2187': 'com_apple_MobileAsset_MobileAccessoryUpdate_DurianFirmware'
    },
    'Beats': {
        'A2048': 'com_apple_MobileAsset_MobileAccessoryUpdate_A2048_EA',
        'A2577': 'com_apple_MobileAsset_MobileAccessoryUpdate_A2577_EA'
    }
}

os_str_map = {
    'AirPods': 'Bluetooth Headset Firmware',
    'AirTags': 'Durian Firmware',
    'Beats': 'Bluetooth Headset Firmware',
}

release_notes_map = {
    'AirPods': 'https://support.apple.com/106340',
    'AirTags': 'https://support.apple.com/102183'
}

device_map = {
    'A2032': [
        "AirPods2,1-left",
        "AirPods2,1-right"
    ],
    'A2048': [
        "PowerbeatsPro1,1",
        "PowerbeatsPro1,1-faze",
        "PowerbeatsPro1,1-fragment",
        "PowerbeatsPro1,1-melody",
        "PowerbeatsPro1,1-nba",
        "PowerbeatsPro1,1-paria",
        "PowerbeatsPro1,1-samuel"
    ],
    'A2084': [
        "AirPods2,2-left",
        "AirPods2,2-right"
    ],
    'A2096': [
        "iProd8,6"
    ],
    'A2187': [
        "AirTag1,1"
    ],
    'A2564': [
        "Audio2,1-left",
        "Audio2,1-right"
    ],
    'A2577': [
        "BeatsFitPro1,1",
        "BeatsFitPro1,1-fragment",
        "BeatsFitPro1,1-kim"
    ],
    'A2618': [
        "AirPods3,1-left",
        "AirPods3,1-right"
    ],
    'A2968': [
        "Device1,8228-case"
    ],
    'A3048': [
        "Device1,8228-left",
        "Device1,8228-right"
    ]
}

files = set()

for asset_type, assets in asset_types.items():
    for model, asset in assets.items():
        if args.beta:
            if not beta_asset_subfolders.get(asset_type):
                break
            asset_url = f'https://mesu.apple.com/assets/{beta_asset_subfolders[asset_type]}/{asset}/{asset}.xml'
        else:
            asset_url = f'https://mesu.apple.com/assets/{asset}/{asset}.xml'
        asset_response = SESSION.get(f"{asset_url}?cachebust{random.randint(100, 1000)}")
        try:
            asset_response.raise_for_status()
        except:
            print(f"Skipping {asset}...")
            continue
        asset_plist = plistlib.loads(asset_response.content)
        for asset in asset_plist['Assets']:
            kern_version = re.search(r"\d+(?=[a-zA-Z])", asset['Build']).group()
            file_path = f"osFiles/{os_str_map[asset_type]}/{kern_version}x/{asset['Build']}.json"

            if not Path(file_path).exists():
                with remotezip.RemoteZip(f"{asset['__BaseURL']}{asset['__RelativePath']}") as file:
                    manifest_paths = [f for f in file.namelist() if f.endswith("BuildManifest.plist")]
                    buildtrain = None
                    version = None
                    if manifest_paths:
                        build_manifest = plistlib.loads(file.read(manifest_paths[0]))
                        buildtrain = build_manifest['BuildIdentities'][0]['Info']['BuildTrain']
                        version = build_manifest['ProductVersion']
                    release_date = datetime.strptime(asset_response.headers.get("Last-Modified").replace(" GMT", ""), '%a, %d %b %Y %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(zoneinfo.ZoneInfo('America/Los_Angeles')).strftime("%Y-%m-%d")
                    if os_str_map[asset_type] == 'Bluetooth Headset Firmware' and not version:
                        if asset['FirmwareVersionMinor'] > 1000:
                            version = '.'.join(str(asset['FirmwareVersionMajor']))
                        else:
                            version = f"{asset['FirmwareVersionMajor']}.{asset['FirmwareVersionMinor']}"
                    elif os_str_map[asset_type] == 'Durian Firmware':
                        version = f"{asset['FirmwareVersionMajor']}.{asset['FirmwareVersionMinor']}.{asset['FirmwareVersionRelease']}"
                    base_contents = {
                        "osStr": os_str_map[asset_type],
                        "version": version,
                        "build": asset['Build'],
                        "released": release_date,
                        "deviceMap": []
                    }
                    if buildtrain:
                        base_contents['buildTrain'] = buildtrain

                    if args.beta:
                        base_contents["beta"] = True
                    elif release_notes_map.get(asset_type):
                        base_contents["releaseNotes"] = release_notes_map[asset_type]
                    json.dump(base_contents, Path(file_path).open("w", encoding="utf-8", newline="\n"), indent=4, ensure_ascii=False)

            file_data = json.load(Path(file_path).open(encoding="utf-8"))
            if device_map[model][0] in file_data['deviceMap']:
                continue
            file_data['deviceMap'].extend(device_map[model])
            source = {"deviceMap": device_map[model], "type": "ota", "links": [{"url": f"{asset['__BaseURL']}{asset['__RelativePath']}", "active": True}]}
            file_data.setdefault('sources', []).append(source)

            json.dump(sort_os_file(None, file_data), Path(file_path).open("w", encoding="utf-8", newline="\n"), indent=4, ensure_ascii=False)

            files.add(Path(file_path))

update_links(list(files))
