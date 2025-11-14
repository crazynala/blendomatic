import bpy
import json
import os
from pathlib import Path

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
RENDER_CONFIG_PATH = "render_config.json"
GARMENTS_DIR = Path("garments")
FABRICS_DIR = Path("fabrics")

# ---------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------
def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def safe_get_obj(name):
    obj = bpy.data.objects.get(name)
    if not obj:
        print(f"[WARN] Object not found: {name}")
    return obj

def select_from_list(items, prompt="Select an option:"):
    for i, item in enumerate(items):
        print(f"{i}: {item}")
    while True:
        choice = input(f"{prompt} (number) > ")
        if choice.isdigit() and 0 <= int(choice) < len(items):
            return items[int(choice)]
        print("[ERROR] Invalid selection, try again.")

# ---------------------------------------------------------
# Material Handling
# ---------------------------------------------------------
def apply_fabric_material(fabric):
    """Creates and assigns a new material based on the fabric config."""
    mat_name = f"MAT_{fabric['name']}"
    if mat_name in bpy.data.materials:
        return bpy.data.materials[mat_name]

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")

    def add_tex_node(label, path, output_socket):
        if not os.path.exists(path):
            print(f"[WARN] Missing texture: {path}")
            return
        tex = nodes.new(type="ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path)
        tex.label = label
        links.new(tex.outputs["Color"], bsdf.inputs[output_socket])

    texs = fabric.get("textures", {})
    if "base_color" in texs:
        add_tex_node("BaseColor", texs["base_color"], "Base Color")
    if "roughness" in texs:
        add_tex_node("Roughness", texs["roughness"], "Roughness")
    if "normal" in texs:
        normal_map = nodes.new(type="ShaderNodeNormalMap")
        tex = nodes.new(type="ShaderNodeTexImage")
        tex.image = bpy.data.images.load(texs["normal"])
        links.new(tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

    p = fabric.get("material_params", {})
    bsdf.inputs["Metallic"].default_value = p.get("metallic", 0.0)
    bsdf.inputs["Roughness"].default_value = p.get("roughness", 0.5)
    bsdf.inputs["Alpha"].default_value = p.get("alpha", 1.0)

    print(f"[INFO] Created material {mat_name}")
    return mat

# ---------------------------------------------------------
# Mesh / Asset Handling
# ---------------------------------------------------------
def configure_mesh_object(mesh_config):
    obj = safe_get_obj(mesh_config["name"])
    if not obj:
        return

    # --- Rendering visibility ---
    obj.hide_render = not mesh_config.get("render", True)
    obj.cycles.is_holdout = mesh_config.get("holdout", False)
    obj.cycles.is_shadow_catcher = mesh_config.get("shadow_catcher", False)

    # --- Viewport visibility ---
    show_in_viewport = mesh_config.get("show_in_viewport", True)
    obj.hide_viewport = not show_in_viewport
    obj.hide_set(not show_in_viewport)

def configure_asset(asset):
    print(f"[INFO] Configuring asset: {asset['name']}")
    for mesh in asset.get("meshes", []):
        configure_mesh_object(mesh)

# ---------------------------------------------------------
# Render Settings
# ---------------------------------------------------------
def apply_render_settings(config):
    scene = bpy.context.scene

    # Engine
    scene.render.engine = config.get("engine", "CYCLES")

    # Resolution
    res = config.get("resolution", {})
    scene.render.resolution_x = res.get("x", 1920)
    scene.render.resolution_y = res.get("y", 1080)
    scene.render.resolution_percentage = res.get("scale", 100)

    # Samples
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = config.get("samples", 16)
        scene.cycles.use_adaptive_sampling = config.get("adaptive_sampling", True)
        scene.cycles.device = config.get("device", "GPU")
        scene.cycles.preview_samples = config.get("preview_samples", 4)

    # Output format
    fmt = config.get("output_format", "PNG").upper()
    scene.render.image_settings.file_format = fmt

    print(f"[INFO] Applied render settings: {config}")

# ---------------------------------------------------------
# Rendering
# ---------------------------------------------------------
def render_asset(garment, fabric, asset, material):
    garment_name = garment.get("output_prefix", "garment")
    fabric_name = fabric["name"].lower().replace(" ", "_")
    suffix = asset.get("suffix", asset["name"].lower().replace(" ", "_"))

    outdir = Path("renders") / garment_name
    outdir.mkdir(parents=True, exist_ok=True)

    filename = f"{garment_name}-{fabric_name}-{suffix}.png"
    outpath = str(outdir / filename)

    bpy.context.scene.render.filepath = outpath
    print(f"[RENDER] {filename}")
    bpy.ops.render.render(write_still=True)

# ---------------------------------------------------------
# Main CLI
# ---------------------------------------------------------
def main():
    # --- Load render config and select mode ---
    render_cfg = load_json(RENDER_CONFIG_PATH)
    mode = select_from_list(list(render_cfg["modes"].keys()), "Choose render mode")
    render_settings = render_cfg["modes"][mode]

    # --- Select garment ---
    garments = [f for f in GARMENTS_DIR.glob("*.json")]
    garment_file = select_from_list([g.name for g in garments], "Choose a garment")
    garment = load_json(GARMENTS_DIR / garment_file)

    # --- Select fabric ---
    fabrics = [f for f in FABRICS_DIR.glob("*.json")]
    fabric_file = select_from_list([f.name for f in fabrics], "Choose a fabric")
    fabric = load_json(FABRICS_DIR / fabric_file)

    # --- Load garment blend file ---
    blend_file = garment.get("blend_file")
    if not blend_file or not os.path.exists(blend_file):
        raise FileNotFoundError(f"Garment blend file not found: {blend_file}")

    print(f"[INFO] Loading garment blend file: {blend_file}")
    bpy.ops.wm.open_mainfile(filepath=blend_file)

    # --- Apply render settings ---
    apply_render_settings(render_settings)

    # --- Apply material ---
    mat = apply_fabric_material(fabric)
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            for slot in obj.material_slots:
                slot.material = mat

    # --- Interactive asset selection ---
    assets = garment.get("assets", [])
    if not assets:
        print("[WARN] No assets found in garment.")
        return

    asset_file = select_from_list([a["name"] for a in assets], "Choose an asset")
    asset_data = next(a for a in assets if a["name"] == asset_file)

    # --- Configure and render ---
    configure_asset(asset_data)
    render_asset(garment, fabric, asset_data, mat)

if __name__ == "__main__":
    main()
