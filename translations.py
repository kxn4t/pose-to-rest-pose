# Translation dictionary for Pose to Rest Pose addon
# Format: {locale: {(context, message): translation, ...}, ...}

translations_dict = {
    "ja_JP": {
        # Operator labels and descriptions
        ("*", "Apply Current Pose as Rest"): "現在のポーズをレストポーズとして適用",
        ("*", "Apply current pose as rest pose while preserving shape keys and drivers"): "シェイプキーとドライバーを保持しながら現在のポーズをレストポーズとして適用",
        
        # Property labels and descriptions
        ("*", "Target Armature"): "対象アーマチュア",
        ("*", "Armature to apply pose to rest position"): "ポーズをレストポーズに適用するアーマチュア",
        
        # Panel UI strings
        ("*", "Apply Current Pose as Rest Pose"): "現在のポーズをレストポーズとして適用",
        
        # Error messages
        ("*", "No armature selected"): "アーマチュアが選択されていません",
        ("*", "Invalid armature object"): "無効なアーマチュアオブジェクト",
        ("*", "Failed to apply pose to armature: {error}"): "アーマチュアへのポーズ適用に失敗しました: {error}",
        ("*", "Failed to process shape keys for {obj_name}"): "{obj_name}のシェイプキー処理に失敗しました",
        ("*", "Error occurred: {error}"): "エラーが発生しました: {error}",
        ("*", "No meshes found with armature modifier"): "アーマチュアモディファイアを持つメッシュが見つかりません",
        ("*", "Object '{obj_name}' has multiple Armature modifiers"): "オブジェクト'{obj_name}'に複数のアーマチュアモディファイアがあります",
        ("*", "Cannot transfer shape key '{shapekey_name}': vertex count mismatch ({base_count} vs {shapekey_count}). Check for modifiers that change vertex count (Decimate, Weld, etc.)."): "シェイプキー'{shapekey_name}'を転送できません: 頂点数が一致しません（{base_count} vs {shapekey_count}）。頂点数を変更するモディファイア（Decimate、Weldなど）を確認してください。",
        ("*", "Shape key transfer failed for '{shapekey_name}': expected {expected_keys} keys, got {actual_keys}"): "'{shapekey_name}'のシェイプキー転送に失敗しました: {expected_keys}個のキーを期待しましたが、{actual_keys}個でした",
        ("*", "Deformation modifiers before Armature modifier detected: {mesh_list}"): "アーマチュアモディファイアより前にデフォームモディファイアが検出されました: {mesh_list}",
        ("*", "Cannot transfer shape key '{shapekey_name}': vertex count mismatch after modifiers"): "シェイプキー'{shapekey_name}'を転送できません: モディファイア後の頂点数が一致しません",
        ("*", "Shape key '{shapekey_name}': {error}"): "シェイプキー'{shapekey_name}': {error}",
        
        # Success messages
        ("*", "Applied pose as rest for {armature_name} and processed {mesh_count} meshes"): "{armature_name}にポーズを適用し、{mesh_count}個のメッシュを処理しました",
    }
}
