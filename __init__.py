# This addon incorporates shape key preservation algorithms inspired by
# SKkeeper addon (https://github.com/smokejohn/SKkeeper) by Johannes Rauch,
# licensed under GPL v3. The core pose-to-rest functionality and data management
# systems are original implementations by kxn4t.

bl_info = {
    "name": "Pose to Rest Pose",
    "author": "kxn4t",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Pose Mode > Pose > Apply",
    "description": "Apply current pose as rest pose while preserving shape keys and drivers",
    "category": "Rigging",
}

import bpy
from bpy.props import PointerProperty
from typing import List, Dict, Any, Optional, Tuple, Union

ShapeKeyDataDict = Dict[str, Any]  # Shape key properties dictionary
ShapeKeyDataList = List[ShapeKeyDataDict]  # List of shape key data
ModifierDataDict = Dict[str, Any]  # Modifier settings dictionary
ObjectNameToDriverState = Dict[str, bool]  # Object name -> driver exists flag
ObjectNameToModifierData = Dict[
    str, Optional[ModifierDataDict]
]  # Object name -> modifier data
ObjectNameToObject = Dict[str, bpy.types.Object]  # Object name -> object reference
MeshObjectList = List[bpy.types.Object]  # List of mesh objects
OriginalStateDict = Dict[str, Any]  # Original context state dictionary
OperatorResultDict = Dict[str, str]  # Blender operator result dictionary
ValidationResult = Tuple[
    bpy.types.Object, MeshObjectList
]  # Armature and affected meshes
ProcessResult = Union[
    bool, Tuple[bool, bpy.types.Object]
]  # Shape key processing result


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def log(msg: str) -> None:
    """Print console message"""
    print(f"<PoseToRest> {msg}")


def copy_object(obj: bpy.types.Object, name_suffix: str = "copy") -> bpy.types.Object:
    """Create a copy of object with new mesh data"""
    copy_obj = obj.copy()
    copy_obj.data = obj.data.copy()
    copy_obj.name = f"{obj.name}_{name_suffix}"
    copy_obj.data.name = f"{obj.data.name}_{name_suffix}"
    bpy.context.collection.objects.link(copy_obj)
    return copy_obj


def delete_object(obj: Optional[bpy.types.Object]) -> None:
    """Safely delete object and its mesh data"""
    try:
        if obj and obj.name in bpy.data.objects:
            if obj.data and obj.data.users == 1:
                mesh_data = obj.data
                bpy.data.objects.remove(obj)
                if mesh_data.name in bpy.data.meshes:
                    bpy.data.meshes.remove(mesh_data)
            else:
                bpy.data.objects.remove(obj)
    except Exception as e:
        log(f"Error deleting object: {e}")


def copy_attributes(source: Any, target: Any) -> None:
    """Copy compatible attributes from source to target"""
    keys = dir(source)
    for key in keys:
        if (
            not key.startswith("_")
            and not key.startswith("error_")
            and key != "group"
            and key != "strips"
            and key != "is_valid"
            and key != "rna_type"
            and key != "bl_rna"
        ):
            try:
                setattr(target, key, getattr(source, key))
            except AttributeError:
                pass


# =============================================================================
# SHAPE KEY OPERATIONS
# =============================================================================


def apply_shape_key(obj: bpy.types.Object, sk_keep: int) -> None:
    """Keep only the specified shape key and bake it into the mesh"""
    if not obj.data.shape_keys:
        return

    shapekeys = obj.data.shape_keys.key_blocks
    if not (0 <= sk_keep < len(shapekeys)):
        return

    # Remove all other shape keys
    for i in reversed(range(len(shapekeys))):
        if i != sk_keep:
            obj.shape_key_remove(shapekeys[i])

    # Remove the remaining one to bake it into the mesh
    if obj.data.shape_keys and len(obj.data.shape_keys.key_blocks) > 0:
        obj.shape_key_remove(obj.data.shape_keys.key_blocks[0])


def add_objs_shapekeys(destination: bpy.types.Object, sources: MeshObjectList) -> None:
    """Add source objects as shape keys to destination"""
    for o in bpy.context.scene.objects:
        o.select_set(False)

    for src in sources:
        src.select_set(True)

    bpy.context.view_layer.objects.active = destination
    bpy.ops.object.join_shapes()


def validate_vertex_count_compatibility(
    base_obj: bpy.types.Object, shapekey_obj: bpy.types.Object, shapekey_name: str
) -> None:
    """Validate that objects have compatible vertex counts for shape key transfer"""
    base_vertex_count = len(base_obj.data.vertices)
    shapekey_vertex_count = len(shapekey_obj.data.vertices)

    if base_vertex_count != shapekey_vertex_count:
        error_msg = (
            f"Cannot transfer shape key '{shapekey_name}': vertex count mismatch "
            f"({base_vertex_count} vs {shapekey_vertex_count}). "
            f"Check for modifiers that change vertex count (Decimate, Weld, etc.)."
        )
        raise ValueError(error_msg)


def validate_shape_key_transfer(
    receiver: bpy.types.Object, expected_shapekey_index: int, shapekey_name: str
) -> None:
    """Validate shape key transfer was successful"""
    # Check if shape keys exist at all
    if receiver.data.shape_keys is None:
        error_msg = f"Cannot transfer shape key '{shapekey_name}': vertex count mismatch after modifiers."
        raise ValueError(error_msg)

    # Check if the correct number of shape keys were transferred
    current_shapekey_count = (
        len(receiver.data.shape_keys.key_blocks) - 1
    )  # Exclude basis
    if current_shapekey_count != expected_shapekey_index:
        error_msg = (
            f"Shape key transfer failed for '{shapekey_name}': "
            f"expected {expected_shapekey_index} keys, got {current_shapekey_count}."
        )
        raise ValueError(error_msg)


# =============================================================================
# MODIFIER OPERATIONS
# =============================================================================


def apply_armature_modifier_only(
    obj: bpy.types.Object, armature: bpy.types.Object
) -> None:
    """Apply only armature modifiers targeting the specified armature"""
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object == armature:
            # Set up selection
            for o in bpy.context.scene.objects:
                o.select_set(False)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj

            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                log(f"Applied armature modifier {modifier.name} on object {obj.name}")
            except RuntimeError as e:
                log(f"Failed to apply armature modifier on {obj.name}: {e}")
                raise e
            break


# =============================================================================
# DATA PRESERVATION CLASSES
# =============================================================================


class ShapeKeyManager:
    """Manages shape key properties and custom data"""

    @staticmethod
    def store_properties(obj: bpy.types.Object) -> Optional[ShapeKeyDataList]:
        """Store all shape key properties including custom properties"""
        if not obj.data.shape_keys:
            return None

        shape_key_data = []
        for sk in obj.data.shape_keys.key_blocks:
            # Safely get custom properties
            custom_props = {}
            try:
                if hasattr(sk, "keys"):
                    custom_props = {
                        key: sk[key] for key in sk.keys() if not key.startswith("_")
                    }
            except (TypeError, AttributeError):
                custom_props = {}

            sk_data = {
                "name": sk.name,
                "value": sk.value,
                "slider_min": sk.slider_min,
                "slider_max": sk.slider_max,
                "mute": sk.mute,
                "interpolation": sk.interpolation,
                "relative_key": sk.relative_key.name if sk.relative_key else None,
                "vertex_group": sk.vertex_group,
                "custom_properties": custom_props,
            }
            shape_key_data.append(sk_data)
        return shape_key_data

    @staticmethod
    def restore_properties(
        obj: bpy.types.Object, shape_key_data: Optional[ShapeKeyDataList]
    ) -> None:
        """Restore shape key properties including custom properties"""
        if not shape_key_data or not obj.data.shape_keys:
            return

        for i, sk_data in enumerate(shape_key_data):
            if i < len(obj.data.shape_keys.key_blocks):
                sk = obj.data.shape_keys.key_blocks[i]
                sk.value = sk_data["value"]
                sk.slider_min = sk_data["slider_min"]
                sk.slider_max = sk_data["slider_max"]
                sk.mute = sk_data["mute"]
                sk.interpolation = sk_data["interpolation"]
                sk.vertex_group = sk_data["vertex_group"]

                # Restore relative key reference
                if sk_data["relative_key"]:
                    for ref_sk in obj.data.shape_keys.key_blocks:
                        if ref_sk.name == sk_data["relative_key"]:
                            sk.relative_key = ref_sk
                            break

                # Restore custom properties
                try:
                    for key, value in sk_data["custom_properties"].items():
                        sk[key] = value
                except (TypeError, AttributeError):
                    log(f"Could not restore custom properties for shape key {sk.name}")


class DriverManager:
    """Manages shape key drivers preservation and restoration"""

    @staticmethod
    def check_drivers_exist(obj: bpy.types.Object) -> bool:
        """Check if drivers exist on shape keys before processing"""
        if (
            not obj.data.shape_keys
            or not obj.data.shape_keys.animation_data
            or not obj.data.shape_keys.animation_data.drivers
        ):
            return False
        return True

    @staticmethod
    def restore_drivers(
        obj: bpy.types.Object, drivers_existed: bool, original_obj: bpy.types.Object
    ) -> None:
        """Restore drivers from original object to processed object"""
        if not drivers_existed or not original_obj.data.shape_keys:
            return

        try:
            # Clear existing drivers
            if obj.data.shape_keys.animation_data:
                obj.data.shape_keys.animation_data_clear()

            # Create animation data
            obj.data.shape_keys.animation_data_create()

            # Transfer drivers using from_existing method
            for orig_driver in original_obj.data.shape_keys.animation_data.drivers:
                obj.data.shape_keys.animation_data.drivers.from_existing(
                    src_driver=orig_driver
                )

            # Fix self-references
            for fcurve in obj.data.shape_keys.animation_data.drivers:
                for variable in fcurve.driver.variables:
                    for target in variable.targets:
                        if target.id == original_obj:
                            target.id = obj

            log(f"Successfully restored drivers for {obj.name}")

        except Exception as e:
            log(f"Failed to restore drivers for {obj.name}: {e}")


class ModifierManager:
    """Manages armature modifier settings"""

    @staticmethod
    def store_armature_modifier(
        obj: bpy.types.Object, armature: bpy.types.Object
    ) -> Optional[ModifierDataDict]:
        """Store armature modifier settings"""
        for i, mod in enumerate(obj.modifiers):
            if mod.type == "ARMATURE" and mod.object == armature:
                return {
                    "name": mod.name,
                    "object": mod.object,
                    "use_deform_preserve_volume": mod.use_deform_preserve_volume,
                    "use_vertex_groups": mod.use_vertex_groups,
                    "use_bone_envelopes": mod.use_bone_envelopes,
                    "vertex_group": mod.vertex_group,
                    "invert_vertex_group": mod.invert_vertex_group,
                    "show_viewport": mod.show_viewport,
                    "show_render": mod.show_render,
                    "show_in_editmode": mod.show_in_editmode,
                    "show_on_cage": getattr(mod, "show_on_cage", False),
                    "index": i,
                }
        return None

    @staticmethod
    def create_armature_modifier(
        obj: bpy.types.Object, mod_data: Optional[ModifierDataDict]
    ) -> None:
        """Create armature modifier with stored settings"""
        if not mod_data:
            return

        mod = obj.modifiers.new(mod_data["name"], "ARMATURE")
        mod.object = mod_data["object"]
        mod.use_deform_preserve_volume = mod_data["use_deform_preserve_volume"]
        mod.use_vertex_groups = mod_data["use_vertex_groups"]
        mod.use_bone_envelopes = mod_data["use_bone_envelopes"]
        mod.vertex_group = mod_data["vertex_group"]
        mod.invert_vertex_group = mod_data["invert_vertex_group"]
        mod.show_viewport = mod_data["show_viewport"]
        mod.show_render = mod_data["show_render"]
        mod.show_in_editmode = mod_data["show_in_editmode"]
        if hasattr(mod, "show_on_cage"):
            mod.show_on_cage = mod_data["show_on_cage"]

        # Move modifier to correct position
        if "index" in mod_data:
            target_index = mod_data["index"]
            current_index = len(obj.modifiers) - 1  # New modifier is added at the end

            # Ensure the object is active and selected before moving the modifier
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)

            # Move the modifier to the target position
            # We need to move UP (towards index 0) to reach the target position
            moves_needed = current_index - target_index
            for _ in range(moves_needed):
                try:
                    bpy.ops.object.modifier_move_up(modifier=mod.name)
                except RuntimeError as e:
                    log(f"Warning: Could not move modifier to target position: {e}")
                    break


# =============================================================================
# MAIN OPERATOR
# =============================================================================


class POSE_TO_REST_OT_apply(bpy.types.Operator):
    bl_idname = "pose_to_rest.apply"
    bl_label = "Apply Current Pose as Rest"
    bl_description = "Apply current pose as rest pose while preserving shape keys and drivers"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Allow if armature is set in scene or active object is armature
        return context.scene.pose_to_rest_armature is not None or (
            context.active_object and context.active_object.type == "ARMATURE"
        )

    def get_armature(self, context: bpy.types.Context) -> Optional[bpy.types.Object]:
        """Get target armature from context or scene"""
        if context.active_object and context.active_object.type == "ARMATURE":
            return context.active_object
        return context.scene.pose_to_rest_armature

    def validate_objects(self, armature: bpy.types.Object) -> MeshObjectList:
        """Validate and collect affected mesh objects"""
        affected_meshes = []
        warning_meshes = []

        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue

            armature_count = sum(
                1
                for mod in obj.modifiers
                if mod.type == "ARMATURE" and mod.object == armature
            )

            if armature_count > 1:
                raise ValueError(f"Object '{obj.name}' has multiple Armature modifiers")
            elif armature_count == 1:
                # Check modifier order
                if self.has_modifier_order_issue(obj, armature):
                    warning_meshes.append(obj.name)
                affected_meshes.append(obj)

        if warning_meshes:
            warning_msg = (
                "Deformation modifiers before Armature modifier detected: "
                + ", ".join(warning_meshes)
            )
            raise ValueError(warning_msg)

        return affected_meshes

    def has_modifier_order_issue(
        self, obj: bpy.types.Object, armature: bpy.types.Object
    ) -> bool:
        """Check if deformation modifiers come before armature modifier"""
        arm_index = next(
            (
                i
                for i, mod in enumerate(obj.modifiers)
                if mod.type == "ARMATURE" and mod.object == armature
            ),
            -1,
        )

        if arm_index == -1:
            return False

        deformation_mods = {
            "MESH_DEFORM",
            "LATTICE",
            "CLOTH",
            "SOFT_BODY",
            "MESH_CACHE",
            "SURFACE_DEFORM",
            "VOLUME_DEFORM",
            "NODES",
            "DISPLACE",
            "WAVE",
            "SHRINKWRAP",
            "SIMPLE_DEFORM",
        }

        return any(mod.type in deformation_mods for mod in obj.modifiers[:arm_index])

    def process_shape_keys_with_pose(
        self, obj: bpy.types.Object, armature: bpy.types.Object
    ) -> ProcessResult:
        """Process shape keys"""
        if not obj.data.shape_keys:
            log(f"No shape keys on {obj.name}, applying armature modifier directly")
            apply_armature_modifier_only(obj, armature)
            return True

        shapekey_names = [block.name for block in obj.data.shape_keys.key_blocks]
        num_shapekeys = len(obj.data.shape_keys.key_blocks)
        log(f"Processing {num_shapekeys} shape keys: {obj.name}")

        # Store shape key properties before processing
        shape_key_props = ShapeKeyManager.store_properties(obj)
        original_obj = obj  # Keep reference for driver restoration

        try:
            # Create receiving object
            receiver = copy_object(obj, "shapekey_receiver")

            apply_shape_key(receiver, 0)  # Keep only base shape key
            apply_armature_modifier_only(receiver, armature)

            # Track successful transfers for cleanup
            successful_transfers = 0

            # Process each shape key (skip base shape key at index 0)
            for shapekey_index in range(1, num_shapekeys):
                shapekey_name = shapekey_names[shapekey_index]
                log(f"Processing shape key {shapekey_index}: {shapekey_name}")

                shapekey_obj = None

                try:
                    # Create copy for this shape key
                    shapekey_obj = copy_object(obj, f"shapekey_{shapekey_index}")
                    apply_shape_key(shapekey_obj, shapekey_index)
                    apply_armature_modifier_only(shapekey_obj, armature)

                    # Pre-transfer validation: Check vertex count compatibility
                    validate_vertex_count_compatibility(
                        receiver, shapekey_obj, shapekey_name
                    )

                    # Add to receiver
                    add_objs_shapekeys(receiver, [shapekey_obj])

                    # Post-transfer validation: Ensure transfer was successful
                    validate_shape_key_transfer(receiver, shapekey_index, shapekey_name)

                    # Restore the shape key name
                    receiver.data.shape_keys.key_blocks[
                        shapekey_index
                    ].name = shapekey_name
                    successful_transfers += 1

                    # Delete the shape key donor
                    delete_object(shapekey_obj)
                    shapekey_obj = None

                    log(f"Successfully transferred shape key: {shapekey_name}")

                except ValueError as ve:
                    # Clean up before re-raising error
                    if shapekey_obj:
                        delete_object(shapekey_obj)
                    log(f"Validation error for shape key {shapekey_name}: {ve}")
                    raise ValueError(f"Shape key '{shapekey_name}': {ve}")
                except Exception as e:
                    # Clean up before re-raising error
                    if shapekey_obj:
                        delete_object(shapekey_obj)
                    log(f"Error processing shape key {shapekey_index}: {e}")
                    raise e

            # Replace the original object's mesh data with the processed receiver's data
            orig_data = obj.data

            # Remove existing armature modifiers BEFORE data replacement
            for mod in list(obj.modifiers):
                if mod.type == "ARMATURE" and mod.object == armature:
                    mod_name = mod.name
                    obj.modifiers.remove(mod)
                    log(f"Removed existing armature modifier {mod_name}")

            # Transfer the processed mesh data to the original object
            obj.data = receiver.data
            obj.data.name = orig_data.name

            # Restore shape key properties
            ShapeKeyManager.restore_properties(obj, shape_key_props)

            # Clean up original mesh data
            try:
                bpy.data.meshes.remove(orig_data)
            except:
                log("Warning: Could not remove original mesh data")

            # Remove receiver object
            try:
                bpy.data.objects.remove(receiver)
            except:
                log("Warning: Could not remove receiver object")

            log(f"Completed {obj.name}: {successful_transfers} shape keys processed")
            return (
                True,
                original_obj,
            )  # Return original object reference for driver restoration

        except Exception as e:
            log(f"Error processing shape keys for {obj.name}: {e}")
            # Clean up any temporary objects that might have been created
            try:
                if "receiver" in locals() and receiver:
                    delete_object(receiver)
            except:
                pass
            return False, None

    def _initialize_and_validate(
        self, context: bpy.types.Context
    ) -> Tuple[Optional[OriginalStateDict], Optional[ValidationResult]]:
        """Initialize operation and validate prerequisites"""
        # Store original state
        original_state = {
            "mode": context.mode,
            "active": context.view_layer.objects.active,
        }

        # Get target armature
        armature = self.get_armature(context)
        if not armature:
            self.report({"ERROR"}, "No armature selected")
            return None, None

        # Validate and collect affected meshes
        log("STEP 1: Validating objects and collecting data")
        affected_meshes = self.validate_objects(armature)

        if not affected_meshes:
            self.report({"WARNING"}, "No meshes found with armature modifier")
            return None, None

        return original_state, (armature, affected_meshes)

    def _collect_and_store_data(
        self, affected_meshes: MeshObjectList, armature: bpy.types.Object
    ) -> Tuple[ObjectNameToDriverState, ObjectNameToModifierData]:
        """Collect and store data for restoration"""
        driver_states = {}
        saved_armature_modifiers = {}

        for obj in affected_meshes:
            log(f"Storing data for mesh: {obj.name}")
            driver_states[obj.name] = DriverManager.check_drivers_exist(obj)
            saved_armature_modifiers[obj.name] = (
                ModifierManager.store_armature_modifier(obj, armature)
            )

        log(f"Found {len(affected_meshes)} meshes to process")
        return driver_states, saved_armature_modifiers

    def _process_all_meshes(
        self, affected_meshes: MeshObjectList, armature: bpy.types.Object
    ) -> Tuple[Optional[MeshObjectList], Optional[ObjectNameToObject]]:
        """Process all affected meshes with shape keys"""
        log("STEP 2: Processing shape keys with current pose")
        processed_meshes = []
        original_objects = {}

        for obj in affected_meshes:
            log(f"Processing mesh object: {obj.name}")

            result = self.process_shape_keys_with_pose(obj, armature)
            if isinstance(result, tuple):
                success, original_obj = result
                if not success:
                    self.report(
                        {"ERROR"}, f"Failed to process shape keys for {obj.name}"
                    )
                    return None, None
                original_objects[obj.name] = original_obj
            else:
                # Handle case where no shape keys (returns True only)
                if not result:
                    self.report(
                        {"ERROR"}, f"Failed to process shape keys for {obj.name}"
                    )
                    return None, None
                original_objects[obj.name] = obj

            processed_meshes.append(obj)

        return processed_meshes, original_objects

    def _apply_pose_to_armature(
        self, context: bpy.types.Context, armature: bpy.types.Object
    ) -> bool:
        """Apply current pose to armature rest pose"""
        log("STEP 3: Applying pose to armature rest pose")
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        context.view_layer.objects.active = armature
        armature.select_set(True)
        bpy.ops.object.mode_set(mode="POSE")

        try:
            bpy.ops.pose.armature_apply()
        except Exception as e:
            self.report({"ERROR"}, f"Failed to apply pose to armature: {e}")
            return False

        # Update the scene to ensure the new rest pose is applied
        bpy.context.view_layer.update()
        return True

    def _restore_all_data(
        self,
        processed_meshes: MeshObjectList,
        saved_armature_modifiers: ObjectNameToModifierData,
        driver_states: ObjectNameToDriverState,
        original_objects: ObjectNameToObject,
    ) -> None:
        """Restore armature modifiers and drivers"""
        log("STEP 4: Restoring armature modifiers and drivers")
        for obj in processed_meshes:
            log(f"Restoring modifiers and drivers for: {obj.name}")

            # Restore armature modifier with original settings
            ModifierManager.create_armature_modifier(
                obj, saved_armature_modifiers[obj.name]
            )
            # Restore drivers with the boolean flag and original object reference
            DriverManager.restore_drivers(
                obj, driver_states[obj.name], original_objects[obj.name]
            )

    def _finalize_operation(
        self,
        context: bpy.types.Context,
        original_state: OriginalStateDict,
        armature: bpy.types.Object,
        processed_meshes: MeshObjectList,
    ) -> OperatorResultDict:
        """Restore original state and report results"""
        log("STEP 5: Restoring original state")
        bpy.ops.object.mode_set(mode="OBJECT")
        context.view_layer.objects.active = armature

        if original_state["mode"] == "POSE":
            bpy.ops.object.mode_set(mode="POSE")

        self.report(
            {"INFO"},
            f"Applied pose as rest for {armature.name} and processed {len(processed_meshes)} meshes",
        )
        return {"FINISHED"}

    def _handle_error_cleanup(self, original_state: OriginalStateDict) -> None:
        """Handle error cleanup and state restoration"""
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
            if original_state["mode"].startswith("POSE"):
                bpy.ops.object.mode_set(mode="POSE")
            bpy.context.view_layer.objects.active = original_state["active"]
        except Exception as restore_error:
            log(f"Failed to restore original state: {restore_error}")

    def execute(self, context: bpy.types.Context) -> OperatorResultDict:
        """Main execution method - coordinates the entire operation"""
        try:
            # Step 1: Initialize and validate
            original_state, validation_result = self._initialize_and_validate(context)
            if not validation_result:
                return {"CANCELLED"}

            armature, affected_meshes = validation_result

            # Step 2: Collect and store data
            driver_states, saved_armature_modifiers = self._collect_and_store_data(
                affected_meshes, armature
            )

            # Step 3: Process all meshes
            processed_meshes, original_objects = self._process_all_meshes(
                affected_meshes, armature
            )
            if not processed_meshes:
                return {"CANCELLED"}

            # Step 4: Apply pose to armature
            if not self._apply_pose_to_armature(context, armature):
                return {"CANCELLED"}

            # Step 5: Restore data
            self._restore_all_data(
                processed_meshes,
                saved_armature_modifiers,
                driver_states,
                original_objects,
            )

            # Step 6: Finalize
            return self._finalize_operation(
                context, original_state, armature, processed_meshes
            )

        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        except Exception as e:
            log(f"Critical error occurred: {e}")
            self.report({"ERROR"}, f"Error occurred: {e}")

            if "original_state" in locals():
                self._handle_error_cleanup(original_state)

            return {"CANCELLED"}


# =============================================================================
# REGISTRATION
# =============================================================================


def pose_apply_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    """Add menu item to Pose > Apply menu"""
    layout = self.layout
    layout.separator()
    layout.operator("pose_to_rest.apply", text="Apply Current Pose as Rest Pose")


def register() -> None:
    bpy.utils.register_class(POSE_TO_REST_OT_apply)
    bpy.types.Scene.pose_to_rest_armature = PointerProperty(
        name="Target Armature",
        description="Armature to apply pose to rest position",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "ARMATURE",
    )
    bpy.types.VIEW3D_MT_pose_apply.append(pose_apply_menu_func)


def unregister() -> None:
    bpy.utils.unregister_class(POSE_TO_REST_OT_apply)
    del bpy.types.Scene.pose_to_rest_armature
    bpy.types.VIEW3D_MT_pose_apply.remove(pose_apply_menu_func)


if __name__ == "__main__":
    register()
