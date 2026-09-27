# Pose to Rest Pose

A Blender addon for applying the current pose as rest pose while preserving shape keys and drivers with a single click.

## Features

- **One-Click Operation**: Apply current pose as rest pose directly from the Pose menu
- **Shape Key Preservation**: Maintains all shape keys including values, slider ranges, mute states, relative keys, and vertex groups
- **Driver Support**: Preserves shape key drivers and automatically updates self-references
- **Multi-Mesh Support**: Handles multiple meshes affected by the same armature

## Requirements
Blender 4.2.0 or higher

> **Note:** For Blender 3.6–4.1, please use [v0.3.0](https://github.com/kxn4t/pose-to-rest-pose/releases/tag/v0.3.0) (final legacy version).

## Installation
1. Open Blender's "Edit" → "Preferences" → "Get Extensions"
2. Open "Repositories" → click "+" → "Add Remote Repository"
3. Enter the URL: `https://kxn4t.github.io/blender-extensions/index.json`
4. Search for "Pose to Rest Pose" and install

## Usage
1. Select your armature and enter **Pose Mode**
2. Position your armature in the desired pose
3. Go to **Pose > Apply > Apply Current Pose as Rest Pose**

### What Happens Automatically
The addon will automatically:
- Detect all meshes with Armature modifiers targeting the selected armature, including those in other scenes
- Preserve all shape keys and their properties
- Apply the current pose to the armature's rest position
- Restore the Armature modifier and drivers

## Limitations & Notes

### Modifier Order and Support
This addon applies only the Armature modifier to the mesh data. Other modifiers stay unchanged, so modifiers such as Mirror or Subdivision Surface do not cause vertex count mismatches.

| Setup | Behavior | Details |
| :--- | :--- | :--- |
| **Armature → Other modifiers** | ✅ Works (recommended) | The ideal modifier order. |
| **Deformation → Armature** | ❌ Cancelled | If a deformation modifier such as Displace or Shrinkwrap comes before the Armature modifier, the result would change after the pose is applied, so the operation is cancelled for safety. |
| **Mirror → Armature** | ⚠️ Warning | The operation runs, but only the original half is posed and the other side becomes a flipped copy of it, so the result is correct **only for symmetric poses**. |

> **Note:** Each mesh can have only one Armature modifier targeting the same armature.

### Other Limitations
- **Shared mesh data (linked duplicates)**: Objects sharing mesh data (e.g., created with `Alt+D`) are not supported. Make them independent first via "Object > Relations > Make Single User > Object & Data".
- **Multiple scenes**: Since `pose.armature_apply()` modifies the armature data itself, the addon checks all scenes in the blend file and processes every target mesh at once.

### Not Preserved
The following data is reset or removed when applying:
- **Shape key animation data**: Keyframes, Actions, and NLA strips on shape keys are not transferred. Apply this addon before creating shape key animations.
- **Armature modifier custom properties**: Custom properties added to the Armature modifier itself will be lost. Standard modifier settings (preserve volume, vertex group, stack position, etc.) are restored.

## Technical Details

### Shape Key Processing
Based on the [SKkeeper](https://github.com/smokejohn/SKkeeper) algorithm, this addon:
- Creates temporary copies of each shape key
- Applies the Armature modifier in the current pose
- Transfers each shape key to the base mesh
- Rebuilds all shape key properties and relationships

### Driver Handling
- Automatically detects existing drivers on shape keys
- Preserves driver expressions and variables
- Reconnects the original references, including self-references to shape key data

## License

GPL v3 License (see LICENSE) - Free for personal and commercial use.

## Credits

This addon was created using shape key preservation algorithms from SKkeeper.

- **Shape Key Algorithms**: [SKkeeper](https://github.com/smokejohn/SKkeeper) by Johannes Rauch
- **License**: GPL v3
