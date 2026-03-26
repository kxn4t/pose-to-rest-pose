# This addon incorporates shape key preservation algorithms inspired by
# SKkeeper addon (https://github.com/smokejohn/SKkeeper) by Johannes Rauch,
# licensed under GPL v3. The core pose-to-rest functionality and data management
# systems are original implementations by kxn4t.

bl_info = {
    "name": "Pose to Rest Pose",
    "author": "kxn4t",
    "version": (0, 2, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Pose Mode > Pose > Apply",
    "description": "Apply current pose as rest pose while preserving shape keys and drivers",
    "category": "Rigging",
}

import bpy
from bpy.props import PointerProperty
from typing import List, Dict, Any, Optional, Tuple

from .translations import translations_dict

ShapeKeyDataDict = Dict[str, Any]  # Shape key properties dictionary
ShapeKeyDataList = List[ShapeKeyDataDict]  # List of shape key data
ModifierDataDict = Dict[str, Any]  # Modifier settings dictionary
ObjectNameToDriverState = Dict[str, bool]  # Object name -> driver exists flag
ObjectNameToModifierData = Dict[
    str, Optional[ModifierDataDict]
]  # Object name -> modifier data
MeshObjectList = List[bpy.types.Object]  # List of mesh objects
OriginalStateDict = Dict[str, Any]  # Original context state dictionary
OperatorResultDict = Dict[str, str]  # Blender operator result dictionary
ValidationResult = Tuple[
    bpy.types.Object, MeshObjectList
]  # Armature and affected meshes
PendingMeshChange = Dict[str, Any]  # Pending shape key data swap


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def log(msg: str) -> None:
    """Print console message"""
    print(f"<PoseToRest> {msg}")


class ViewLayerScope:
    """Temporarily link objects into the current view layer for bpy.ops access.

    Objects already in the view layer are left untouched.
    On exit, per-view-layer hidden state is restored and temporary links are removed.
    """

    def __init__(self, *objects: bpy.types.Object):
        self.objects = objects
        self.linked: List[Tuple[bpy.types.Object, bpy.types.Collection]] = []
        self.hidden: List[bpy.types.Object] = []
        self.unhidden_lcs: List[bpy.types.LayerCollection] = []

    def __enter__(self) -> "ViewLayerScope":
        vl = bpy.context.view_layer
        for obj in self.objects:
            if vl.objects.get(obj.name) is None:
                col = self._find_visible_collection(vl)
                if obj.name not in col.objects:
                    col.objects.link(obj)
                    self.linked.append((obj, col))
                # Ensure visibility whether newly linked or already in collection
                self._ensure_collection_visible(vl, col)
                for uc in obj.users_collection:
                    self._ensure_collection_visible(vl, uc)
                vl.update()
            else:
                self._ensure_object_collection_visible(vl, obj)
            if obj.hide_get(view_layer=vl):
                obj.hide_set(False, view_layer=vl)
                self.hidden.append(obj)
        return self

    def __exit__(self, *exc: Any) -> bool:
        vl = bpy.context.view_layer
        for obj in self.hidden:
            try:
                obj.hide_set(True, view_layer=vl)
            except Exception:
                pass
        for obj, col in self.linked:
            try:
                col.objects.unlink(obj)
            except Exception:
                pass
        for lc in reversed(self.unhidden_lcs):
            try:
                lc.hide_viewport = True
            except Exception:
                pass
        return False

    def _ensure_collection_visible(
        self, vl: bpy.types.ViewLayer, collection: bpy.types.Collection
    ) -> None:
        """Temporarily unhide the LayerCollection chain leading to *collection*."""
        def unhide_chain(
            layer_col: bpy.types.LayerCollection,
            target: bpy.types.Collection,
        ) -> bool:
            if layer_col.collection == target:
                if layer_col.hide_viewport:
                    layer_col.hide_viewport = False
                    self.unhidden_lcs.append(layer_col)
                return True
            for child in layer_col.children:
                if unhide_chain(child, target):
                    if layer_col.hide_viewport:
                        layer_col.hide_viewport = False
                        self.unhidden_lcs.append(layer_col)
                    return True
            return False
        unhide_chain(vl.layer_collection, collection)

    def _ensure_object_collection_visible(
        self, vl: bpy.types.ViewLayer, obj: bpy.types.Object
    ) -> None:
        """Unhide the LayerCollection chain for an object already in the view layer."""
        for col in obj.users_collection:
            self._ensure_collection_visible(vl, col)

    @staticmethod
    def _find_visible_collection(
        vl: bpy.types.ViewLayer,
    ) -> bpy.types.Collection:
        """Return a collection reachable from the current view layer."""
        active = vl.active_layer_collection
        if active and active.is_visible:
            return active.collection

        def find_visible(
            layer_col: bpy.types.LayerCollection,
        ) -> Optional[bpy.types.Collection]:
            if layer_col.is_visible:
                return layer_col.collection
            for child in layer_col.children:
                result = find_visible(child)
                if result:
                    return result
            return None

        result = find_visible(vl.layer_collection)
        return result or bpy.context.scene.collection


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
    with ViewLayerScope(destination, *sources):
        for o in bpy.context.view_layer.objects:
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
        error_msg = bpy.app.translations.pgettext(
            "Cannot transfer shape key '{shapekey_name}': vertex count mismatch ({base_count} vs {shapekey_count}). Check for modifiers that change vertex count (Decimate, Weld, etc.)."
        ).format(
            shapekey_name=shapekey_name,
            base_count=base_vertex_count,
            shapekey_count=shapekey_vertex_count,
        )
        raise ValueError(error_msg)


def validate_shape_key_transfer(
    receiver: bpy.types.Object, expected_shapekey_index: int, shapekey_name: str
) -> None:
    """Validate shape key transfer was successful"""
    # Check if shape keys exist at all
    if receiver.data.shape_keys is None:
        error_msg = bpy.app.translations.pgettext(
            "Cannot transfer shape key '{shapekey_name}': vertex count mismatch after modifiers"
        ).format(shapekey_name=shapekey_name)
        raise ValueError(error_msg)

    # Check if the correct number of shape keys were transferred
    current_shapekey_count = (
        len(receiver.data.shape_keys.key_blocks) - 1
    )  # Exclude basis
    if current_shapekey_count != expected_shapekey_index:
        error_msg = bpy.app.translations.pgettext(
            "Shape key transfer failed for '{shapekey_name}': expected {expected_keys} keys, got {actual_keys}"
        ).format(
            shapekey_name=shapekey_name,
            expected_keys=expected_shapekey_index,
            actual_keys=current_shapekey_count,
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
            with ViewLayerScope(obj, armature):
                # Set up selection
                for o in bpy.context.view_layer.objects:
                    o.select_set(False)
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj

                try:
                    # Store modifier name before applying (important for stability)
                    mod_name = modifier.name
                    bpy.ops.object.modifier_apply(modifier=mod_name)
                    log(f"Applied armature modifier {mod_name} on object {obj.name}")
                except RuntimeError as e:
                    log(f"Failed to apply armature modifier on {obj.name}: {e}")
                    raise
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
                sk.name = sk_data["name"]
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
        obj: bpy.types.Object,
        drivers_existed: bool,
        original_shape_keys: Optional[bpy.types.Key],
    ) -> None:
        """Restore drivers from original shape keys to processed object.

        Raises on failure so the caller can handle it in the post-destructive zone.
        """
        if not drivers_existed or not original_shape_keys:
            return
        if not original_shape_keys.animation_data:
            return

        new_shape_keys = obj.data.shape_keys
        if not new_shape_keys:
            raise RuntimeError(
                f"Cannot restore drivers for {obj.name}: new shape keys missing"
            )

        # Clear existing drivers
        if new_shape_keys.animation_data:
            new_shape_keys.animation_data_clear()

        # Create animation data
        new_shape_keys.animation_data_create()

        # Transfer drivers one by one so a single failure doesn't
        # leave already-copied drivers without the remap pass.
        failed_paths: List[str] = []
        for orig_driver in original_shape_keys.animation_data.drivers:
            try:
                new_shape_keys.animation_data.drivers.from_existing(
                    src_driver=orig_driver
                )
            except Exception as e:
                failed_paths.append(orig_driver.data_path)
                log(f"Could not copy driver {orig_driver.data_path} for {obj.name}: {e}")

        # Remap old Key datablock references to new Key
        for fcurve in new_shape_keys.animation_data.drivers:
            for variable in fcurve.driver.variables:
                for target in variable.targets:
                    if (
                        target.id_type == "KEY"
                        and target.id == original_shape_keys
                    ):
                        target.id = new_shape_keys

        if failed_paths:
            raise RuntimeError(
                f"Failed to copy {len(failed_paths)} driver(s) for {obj.name}: "
                + ", ".join(failed_paths)
            )

        log(f"Successfully restored drivers for {obj.name}")


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
            with ViewLayerScope(obj):
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
    bl_description = (
        "Apply current pose as rest pose while preserving shape keys and drivers"
    )
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
        shared_meshes = []
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
                error_msg = bpy.app.translations.pgettext(
                    "Object '{obj_name}' has multiple Armature modifiers"
                ).format(obj_name=obj.name)
                raise ValueError(error_msg)
            elif armature_count == 1:
                if obj.data.users > 1:
                    # Abort the whole operation after the scan so we can report
                    # every mesh that still shares its data.
                    shared_meshes.append(obj.name)
                    continue

                # Check modifier order
                if self.has_modifier_order_issue(obj, armature):
                    warning_meshes.append(obj.name)
                affected_meshes.append(obj)

        if shared_meshes:
            error_msg = bpy.app.translations.pgettext(
                "Objects with shared mesh data are not supported. Make them single-user first: {mesh_list}"
            ).format(mesh_list=", ".join(shared_meshes))
            raise ValueError(error_msg)

        if warning_meshes:
            warning_msg = bpy.app.translations.pgettext(
                "Deformation modifiers before Armature modifier detected: {mesh_list}"
            ).format(mesh_list=", ".join(warning_meshes))
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

    def _prepare_shape_keys_with_pose(
        self, obj: bpy.types.Object, armature: bpy.types.Object
    ) -> PendingMeshChange:
        """Prepare shape keys with pose applied, without modifying the original object.

        Creates a receiver with all shape keys baked with the current pose.
        Raises on failure (caller is responsible for cleaning up pending receivers).
        """
        shapekey_names = [block.name for block in obj.data.shape_keys.key_blocks]
        num_shapekeys = len(shapekey_names)
        log(f"Processing {num_shapekeys} shape keys: {obj.name}")

        shape_key_props = ShapeKeyManager.store_properties(obj)

        receiver = copy_object(obj, "shapekey_receiver")
        try:
            apply_shape_key(receiver, 0)  # Keep only base shape key
            apply_armature_modifier_only(receiver, armature)

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

                    validate_vertex_count_compatibility(
                        receiver, shapekey_obj, shapekey_name
                    )
                    # Add to receiver
                    add_objs_shapekeys(receiver, [shapekey_obj])
                    validate_shape_key_transfer(
                        receiver, shapekey_index, shapekey_name
                    )

                    # Restore the shape key name
                    receiver.data.shape_keys.key_blocks[
                        shapekey_index
                    ].name = shapekey_name
                    successful_transfers += 1

                    delete_object(shapekey_obj)
                    shapekey_obj = None
                    log(f"Successfully transferred shape key: {shapekey_name}")

                except ValueError as ve:
                    if shapekey_obj:
                        delete_object(shapekey_obj)
                    log(f"Validation error for shape key {shapekey_name}: {ve}")
                    error_msg = bpy.app.translations.pgettext(
                        "Shape key '{shapekey_name}': {error}"
                    ).format(shapekey_name=shapekey_name, error=ve)
                    raise ValueError(error_msg)
                except Exception as e:
                    if shapekey_obj:
                        delete_object(shapekey_obj)
                    log(f"Error processing shape key {shapekey_index}: {e}")
                    raise

            log(f"Prepared {obj.name}: {successful_transfers} shape keys")
            return {
                "obj": obj,
                "receiver": receiver,
                "shape_key_props": shape_key_props,
                "successful_transfers": successful_transfers,
            }

        except Exception:
            delete_object(receiver)
            raise

    def _prepare_no_shapekey_mesh(
        self, obj: bpy.types.Object, armature: bpy.types.Object
    ) -> PendingMeshChange:
        """Prepare a mesh without shape keys by applying the armature on a copy."""
        log(f"No shape keys on {obj.name}, preparing copy with armature applied")
        receiver = copy_object(obj, "no_sk_receiver")
        try:
            apply_armature_modifier_only(receiver, armature)
        except Exception:
            delete_object(receiver)
            raise
        return {
            "obj": obj,
            "receiver": receiver,
            "shape_key_props": None,
            "successful_transfers": 0,
        }

    def _commit_mesh_changes(
        self,
        pending_changes: List[PendingMeshChange],
        armature: bpy.types.Object,
    ) -> Tuple[
        Dict[str, Optional[bpy.types.Key]], List[bpy.types.Mesh]
    ]:
        """Apply all pending mesh data swaps.

        Called in the post-destructive zone after pose.armature_apply() succeeds.
        Returns (original_shape_keys_map, deferred_cleanup).
        """
        log("STEP 5: Committing mesh data swaps")
        original_shape_keys_map: Dict[str, Optional[bpy.types.Key]] = {}
        deferred_cleanup: List[bpy.types.Mesh] = []

        for change in pending_changes:
            obj = change["obj"]
            receiver = change["receiver"]
            shape_key_props = change["shape_key_props"]

            orig_data = obj.data
            original_shape_keys_map[obj.name] = orig_data.shape_keys

            # Remove armature modifiers targeting this armature
            for mod in list(obj.modifiers):
                if mod.type == "ARMATURE" and mod.object == armature:
                    mod_name = mod.name
                    obj.modifiers.remove(mod)
                    log(f"Removed existing armature modifier {mod_name}")

            # Rename originals first so the replacement data can reuse the names.
            old_mesh_name = orig_data.name
            old_key_name = orig_data.shape_keys.name if orig_data.shape_keys else None

            orig_data.name = old_mesh_name + "_old_temp"
            if old_key_name is not None and orig_data.shape_keys:
                orig_data.shape_keys.name = old_key_name + "_old_temp"

            obj.data = receiver.data
            obj.data.name = old_mesh_name
            if old_key_name is not None and obj.data.shape_keys:
                obj.data.shape_keys.name = old_key_name

            # Restore shape key properties
            if shape_key_props:
                ShapeKeyManager.restore_properties(obj, shape_key_props)

            # Keep orig_data alive for driver restoration
            deferred_cleanup.append(orig_data)

            # Remove receiver object (mesh data now owned by obj)
            try:
                bpy.data.objects.remove(receiver)
            except Exception as e:
                log(f"Warning: Could not remove receiver object: {e}")

            log(
                f"Committed changes for {obj.name}: "
                f"{change['successful_transfers']} shape keys"
            )

        return original_shape_keys_map, deferred_cleanup

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
        log("STEP 2: Collecting and storing data for restoration")
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

    def _prepare_all_meshes(
        self, affected_meshes: MeshObjectList, armature: bpy.types.Object
    ) -> Optional[List[PendingMeshChange]]:
        """Prepare all affected meshes non-destructively.

        Returns a list of PendingMeshChange dicts on success, or None on failure.
        On failure all receivers are cleaned up automatically.
        """
        log("STEP 3: Preparing shape keys with current pose")
        pending_changes: List[PendingMeshChange] = []

        try:
            for obj in affected_meshes:
                log(f"Preparing mesh object: {obj.name}")
                if obj.data.shape_keys:
                    change = self._prepare_shape_keys_with_pose(obj, armature)
                else:
                    change = self._prepare_no_shapekey_mesh(obj, armature)
                pending_changes.append(change)
        except Exception as e:
            # Clean up all receivers created so far
            for change in pending_changes:
                delete_object(change["receiver"])
            error_msg = bpy.app.translations.pgettext(
                "Failed to process shape keys for {obj_name}"
            ).format(obj_name=obj.name)
            self.report({"ERROR"}, f"{error_msg}: {e}")
            return None

        return pending_changes

    def _apply_pose_to_armature(
        self, context: bpy.types.Context, armature: bpy.types.Object
    ) -> None:
        """Apply current pose to armature rest pose. Raises on failure."""
        log("STEP 4: Applying pose to armature rest pose")

        if not armature:
            raise RuntimeError("Invalid armature object")

        with ViewLayerScope(armature):
            if bpy.context.view_layer.objects.active:
                bpy.ops.object.mode_set(mode="OBJECT")

            # Clear all selections
            bpy.ops.object.select_all(action="DESELECT")

            # Set the armature as active and selected
            context.view_layer.objects.active = armature
            armature.select_set(True)

            # Apply the pose to rest pose
            bpy.ops.object.mode_set(mode="POSE")
            bpy.ops.pose.armature_apply()
            bpy.context.view_layer.update()

    def _restore_all_data(
        self,
        processed_meshes: MeshObjectList,
        saved_armature_modifiers: ObjectNameToModifierData,
        driver_states: ObjectNameToDriverState,
        original_shape_keys_map: Dict[str, Optional[bpy.types.Key]],
    ) -> List[str]:
        """Restore armature modifiers and drivers for every processed mesh.

        Never raises — collects per-object errors and returns them so that
        the caller can report without aborting the remaining meshes.
        """
        log("STEP 6: Restoring armature modifiers and drivers")
        errors: List[str] = []
        for obj in processed_meshes:
            log(f"Restoring modifiers and drivers for: {obj.name}")

            try:
                ModifierManager.create_armature_modifier(
                    obj, saved_armature_modifiers[obj.name]
                )
            except Exception as e:
                log(f"Failed to restore modifier for {obj.name}: {e}")
                errors.append(f"{obj.name} (modifier): {e}")

            try:
                DriverManager.restore_drivers(
                    obj, driver_states[obj.name], original_shape_keys_map[obj.name]
                )
            except Exception as e:
                log(f"Failed to restore drivers for {obj.name}: {e}")
                errors.append(f"{obj.name} (drivers): {e}")

        return errors

    def _finalize_operation(
        self,
        context: bpy.types.Context,
        original_state: OriginalStateDict,
        armature: bpy.types.Object,
        processed_meshes: MeshObjectList,
    ) -> None:
        """Restore original context state and report success."""
        log("STEP 7: Restoring original state")
        original_active = original_state.get("active")
        restore_target = original_active if original_active else armature

        with ViewLayerScope(restore_target):
            context.view_layer.objects.active = restore_target
            restore_target.select_set(True)
            bpy.context.view_layer.update()
            bpy.ops.object.mode_set(mode="OBJECT")

            if original_state["mode"] == "POSE":
                bpy.ops.object.mode_set(mode="POSE")

        success_msg = bpy.app.translations.pgettext(
            "Applied pose as rest for {armature_name} and processed {mesh_count} meshes"
        ).format(armature_name=armature.name, mesh_count=len(processed_meshes))
        self.report({"INFO"}, success_msg)

    def _restore_context(self, original_state: OriginalStateDict) -> None:
        """Best-effort context restoration for error paths."""
        try:
            original_active = original_state.get("active")
            with ViewLayerScope(*([original_active] if original_active else [])):
                bpy.ops.object.mode_set(mode="OBJECT")
                if original_active:
                    bpy.context.view_layer.objects.active = original_active
                if original_state["mode"].startswith("POSE"):
                    bpy.ops.object.mode_set(mode="POSE")
        except Exception as e:
            log(f"Failed to restore context: {e}")

    @staticmethod
    def _cleanup_receivers(
        pending_changes: Optional[List[PendingMeshChange]],
    ) -> None:
        """Delete all receiver objects from pending changes."""
        if not pending_changes:
            return
        for change in pending_changes:
            receiver = change.get("receiver")
            if receiver:
                delete_object(receiver)

    def execute(self, context: bpy.types.Context) -> OperatorResultDict:
        """Main execution method - coordinates the entire operation.

        Pre-destructive zone (Steps 1-3): failures return CANCELLED.
        Post-destructive zone (Steps 4+): failures return FINISHED for undo step.
        """
        original_state = None
        armature = None
        pending_changes = None

        try:
            # === PRE-DESTRUCTIVE ZONE — CANCELLED is safe ===

            # Step 1: Initialize and validate
            original_state, validation_result = self._initialize_and_validate(context)
            if not validation_result:
                return {"CANCELLED"}

            armature, affected_meshes = validation_result

            # Step 2: Collect and store data
            driver_states, saved_armature_modifiers = self._collect_and_store_data(
                affected_meshes, armature
            )

            # Step 3: Prepare all meshes (non-destructive)
            pending_changes = self._prepare_all_meshes(affected_meshes, armature)
            if not pending_changes:
                return {"CANCELLED"}

        except ValueError as e:
            self.report({"ERROR"}, str(e))
            self._cleanup_receivers(pending_changes)
            return {"CANCELLED"}
        except Exception as e:
            log(f"Error during preparation: {e}")
            error_msg = bpy.app.translations.pgettext(
                "Error occurred: {error}"
            ).format(error=e)
            self.report({"ERROR"}, error_msg)
            self._cleanup_receivers(pending_changes)
            return {"CANCELLED"}

        # === POST-DESTRUCTIVE ZONE — always return FINISHED ===
        processed_meshes = [c["obj"] for c in pending_changes]

        try:
            # Step 4: Apply pose to armature
            self._apply_pose_to_armature(context, armature)
        except Exception as e:
            log(f"Failed to apply pose to armature: {e}")
            error_msg = bpy.app.translations.pgettext(
                "Failed to apply pose to armature: {error}"
            ).format(error=e)
            self.report({"ERROR"}, error_msg)
            self._cleanup_receivers(pending_changes)
            if original_state:
                self._restore_context(original_state)
            return {"FINISHED"}

        deferred_cleanup: List[bpy.types.Mesh] = []
        try:
            # Step 5: Commit all mesh changes
            original_shape_keys_map, deferred_cleanup = self._commit_mesh_changes(
                pending_changes, armature
            )
            pending_changes = None  # receivers consumed

            # Step 6: Restore modifiers and drivers
            restore_errors = self._restore_all_data(
                processed_meshes,
                saved_armature_modifiers,
                driver_states,
                original_shape_keys_map,
            )

            if restore_errors:
                error_summary = "; ".join(restore_errors)
                log(f"Restore errors: {error_summary}")
                self.report({"WARNING"}, f"Partial restore failures: {error_summary}")

            # Step 7: Finalize
            self._finalize_operation(
                context, original_state, armature, processed_meshes
            )

        except Exception as e:
            log(f"Error in post-destructive zone: {e}")
            error_msg = bpy.app.translations.pgettext(
                "Error occurred: {error}"
            ).format(error=e)
            self.report({"ERROR"}, error_msg)
            if original_state:
                self._restore_context(original_state)
        finally:
            # Always clean up original mesh data to avoid orphans
            for mesh_data in deferred_cleanup:
                try:
                    bpy.data.meshes.remove(mesh_data)
                except Exception as e:
                    log(f"Warning: Could not remove original mesh data: {e}")

        return {"FINISHED"}


# =============================================================================
# REGISTRATION
# =============================================================================


def pose_apply_menu_func(self: bpy.types.Menu, context: bpy.types.Context) -> None:
    """Add menu item to Pose > Apply menu"""
    layout = self.layout
    layout.separator()
    layout.operator("pose_to_rest.apply", text=bpy.app.translations.pgettext("Apply Current Pose as Rest Pose"))


def register() -> None:
    bpy.utils.register_class(POSE_TO_REST_OT_apply)
    bpy.types.Scene.pose_to_rest_armature = PointerProperty(
        name="Target Armature",
        description="Armature to apply pose to rest position",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "ARMATURE",
    )
    bpy.types.VIEW3D_MT_pose_apply.append(pose_apply_menu_func)
    bpy.app.translations.register(__name__, translations_dict)


def unregister() -> None:
    bpy.utils.unregister_class(POSE_TO_REST_OT_apply)
    del bpy.types.Scene.pose_to_rest_armature
    bpy.types.VIEW3D_MT_pose_apply.remove(pose_apply_menu_func)
    bpy.app.translations.unregister(__name__)


if __name__ == "__main__":
    register()
