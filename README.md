# Pose to Rest Pose

A Blender addon for applying the current pose as rest pose while preserving shape keys and drivers with a single click.

## Features

- **One-Click Operation**: Apply current pose as rest pose directly from the Pose menu
- **Shape Key Preservation**: Maintains all shape keys including values, slider ranges, mute states, and custom properties
- **Driver Support**: Preserves shape key drivers and automatically updates self-references
- **Multi-Mesh Support**: Handles multiple meshes affected by the same armature

## Installation

1. Open Blender and go to Edit → Preferences → Add-ons
2. Click "Install from Disk..."
3. Select the downloaded `pose-to-rest-pose.zip` file
4. Enable the addon by checking the box next to "Pose to Rest Pose" in the addon list

## Usage

### Basic Usage
1. Select your armature and enter **Pose Mode**
2. Position your armature in the desired pose
3. Go to **Pose > Apply > Apply Current Pose as Rest Pose**

The addon will automatically:
- Detect all meshes with Armature modifiers targeting the selected armature
- Preserve all shape keys and their properties
- Apply the current pose to the armature's rest position
- Restore all modifiers and drivers

## Technical Details

### Shape Key Processing
This addon uses algorithms from [SKkeeper](https://github.com/smokejohn/SKkeeper) to:
- Create temporary copies of each shape key
- Apply the armature modifier with the current pose
- Transfer shape keys back to the base mesh
- Maintain all shape key properties and relationships

### Driver Handling
- Automatically detects existing drivers on shape keys
- Preserves driver expressions and variables
- Updates self-references when objects are replaced
- Restores all driver relationships

## Requirements

- Blender 3.6 or higher
- Meshes must have only one Armature modifier per target armature

## Limitations & Best Practices

### Modifier Order
For optimal results, ensure proper modifier order:
- ✅ **Recommended**: Armature Modifier → Other Deformation Modifiers
- ❌ **Not Recommended**: Deformation Modifiers → Armature Modifier

Deformation modifiers (Displace, Wave, Shrinkwrap, etc.) placed before the Armature modifier may cause vertex count mismatches during shape key transfer.
Modifiers that may change vertex count should also be handled with care.

## License

GPL v3 License (see LICENSE) - Free for personal and commercial use.

## Credits

This addon was created using shape key preservation algorithms from SKkeeper.

- **Shape Key Algorithms**: [SKkeeper](https://github.com/smokejohn/SKkeeper) by Johannes Rauch
- **License**: GPL v3
