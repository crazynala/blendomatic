"""
Render Session - Core engine for Blender render automation
Separates business logic from UI concerns
"""
import bpy
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
RENDER_CONFIG_PATH = "render_config.json"
GARMENTS_DIR = Path("garments")
FABRICS_DIR = Path("fabrics")


class RenderSession:
    """
    Core render session that manages state and provides methods for
    interactive rendering without being tied to any specific UI
    """
    
    def __init__(self):
        self.render_cfg = self._load_json(RENDER_CONFIG_PATH)
        
        # Current selections
        self.mode: Optional[str] = None
        self.render_settings: Optional[Dict] = None
        self.garment: Optional[Dict] = None
        self.fabric: Optional[Dict] = None
        self.asset: Optional[Dict] = None
        self.material: Optional[Any] = None
        
        # Available options (loaded once)
        self.garments = list(GARMENTS_DIR.glob("*.json"))
        self.fabrics = list(FABRICS_DIR.glob("*.json"))
        
        # Status tracking
        self._garment_loaded = False
        self._fabric_applied = False
    
    # ---------------------------------------------------------
    # Utility Methods
    # ---------------------------------------------------------
    
    def _load_json(self, path: Path) -> Dict:
        """Load JSON file with error handling"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {e}")
    
    def _safe_get_obj(self, name: str):
        """Safely get Blender object by name"""
        obj = bpy.data.objects.get(name)
        if not obj:
            print(f"[WARN] Object not found: {name}")
        return obj
    
    # ---------------------------------------------------------
    # State Query Methods
    # ---------------------------------------------------------
    
    def list_modes(self) -> List[str]:
        """Get available render modes"""
        return list(self.render_cfg["modes"].keys())
    
    def list_garments(self) -> List[str]:
        """Get available garment files"""
        return [g.name for g in self.garments]
    
    def list_fabrics(self) -> List[str]:
        """Get available fabric files"""
        return [f.name for f in self.fabrics]
    
    def list_assets(self) -> List[str]:
        """Get available assets for current garment"""
        if not self.garment:
            return []
        return [a["name"] for a in self.garment.get("assets", [])]
    
    def get_state(self) -> Dict[str, Any]:
        """Get current session state"""
        return {
            "mode": self.mode,
            "garment_name": self.garment.get("name") if self.garment else None,
            "garment_prefix": self.garment.get("output_prefix") if self.garment else None,
            "fabric_name": self.fabric["name"] if self.fabric else None,
            "asset_name": self.asset["name"] if self.asset else None,
            "garment_loaded": self._garment_loaded,
            "fabric_applied": self._fabric_applied,
            "ready_to_render": self.is_ready_to_render()
        }
    
    def is_ready_to_render(self) -> bool:
        """Check if all required components are set for rendering"""
        return all([
            self.mode,
            self.garment,
            self.fabric,
            self.asset,
            self.material,
            self._garment_loaded,
            self._fabric_applied
        ])
    
    # ---------------------------------------------------------
    # Configuration Methods
    # ---------------------------------------------------------
    
    def set_mode(self, mode_name: str) -> None:
        """Set render mode and apply settings"""
        if mode_name not in self.render_cfg["modes"]:
            available = ", ".join(self.list_modes())
            raise ValueError(f"Unknown mode '{mode_name}'. Available: {available}")
        
        self.mode = mode_name
        self.render_settings = self.render_cfg["modes"][mode_name]
        self._apply_render_settings(self.render_settings)
        print(f"[INFO] Set render mode: {mode_name}")
    
    def set_garment(self, garment_name: str) -> None:
        """Set garment and load its blend file"""
        match = next((g for g in self.garments if g.name == garment_name), None)
        if not match:
            available = ", ".join(self.list_garments())
            raise ValueError(f"Unknown garment '{garment_name}'. Available: {available}")
        
        self.garment = self._load_json(match)
        
        # Load blend file
        blend_file = self.garment.get("blend_file")
        if not blend_file or not os.path.exists(blend_file):
            raise FileNotFoundError(f"Garment blend file not found: {blend_file}")
        
        print(f"[INFO] Loading garment blend file: {blend_file}")
        bpy.ops.wm.open_mainfile(filepath=blend_file)
        
        # Reset dependent state
        self.asset = None
        self._garment_loaded = True
        self._fabric_applied = False
        
        print(f"[INFO] Set garment: {self.garment['name']}")
    
    def set_fabric(self, fabric_name: str) -> None:
        """Set fabric and apply material"""
        match = next((f for f in self.fabrics if f.name == fabric_name), None)
        if not match:
            available = ", ".join(self.list_fabrics())
            raise ValueError(f"Unknown fabric '{fabric_name}'. Available: {available}")
        
        self.fabric = self._load_json(match)
        self.material = self._apply_fabric_material(self.fabric)
        
        # Apply material to all mesh objects
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                for slot in obj.material_slots:
                    slot.material = self.material
        
        self._fabric_applied = True
        print(f"[INFO] Set fabric: {self.fabric['name']}")
    
    def set_asset(self, asset_name: str) -> None:
        """Set asset and configure mesh objects"""
        if not self.garment:
            raise RuntimeError("Select a garment first.")
        
        assets = self.garment.get("assets", [])
        asset = next((a for a in assets if a["name"] == asset_name), None)
        if not asset:
            available = ", ".join(self.list_assets())
            raise ValueError(f"Unknown asset '{asset_name}'. Available: {available}")
        
        self.asset = asset
        self._configure_asset(self.asset)
        print(f"[INFO] Set asset: {asset_name}")
    
    # ---------------------------------------------------------
    # Render Method
    # ---------------------------------------------------------
    
    def render(self) -> str:
        """Perform render with current settings"""
        if not self.is_ready_to_render():
            missing = []
            if not self.mode: missing.append("mode")
            if not self.garment: missing.append("garment")
            if not self.fabric: missing.append("fabric")
            if not self.asset: missing.append("asset")
            if not self._garment_loaded: missing.append("garment blend file")
            if not self._fabric_applied: missing.append("fabric material")
            
            raise RuntimeError(f"Missing components: {', '.join(missing)}")
        
        # Generate output path
        garment_name = self.garment.get("output_prefix", "garment")
        fabric_name = self.fabric["name"].lower().replace(" ", "_")
        asset_suffix = self.asset.get("suffix", self.asset["name"].lower().replace(" ", "_"))
        
        outdir = Path("renders") / garment_name
        outdir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{garment_name}-{fabric_name}-{asset_suffix}.png"
        outpath = str(outdir / filename)
        
        # Render
        bpy.context.scene.render.filepath = outpath
        print(f"[RENDER] Starting render: {filename}")
        bpy.ops.render.render(write_still=True)
        print(f"[RENDER] Completed: {outpath}")
        
        return outpath
    
    # ---------------------------------------------------------
    # Internal Helper Methods
    # ---------------------------------------------------------
    
    def _apply_render_settings(self, config: Dict) -> None:
        """Apply render configuration to Blender scene"""
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
    
    def _apply_fabric_material(self, fabric: Dict):
        """Create and assign material based on fabric config"""
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
    
    def _configure_mesh_object(self, mesh_config: Dict) -> None:
        """Configure individual mesh object based on config"""
        obj = self._safe_get_obj(mesh_config["name"])
        if not obj:
            return
        
        # Rendering visibility
        obj.hide_render = not mesh_config.get("render", True)
        obj.cycles.is_holdout = mesh_config.get("holdout", False)
        obj.cycles.is_shadow_catcher = mesh_config.get("shadow_catcher", False)
        
        # Viewport visibility
        show_in_viewport = mesh_config.get("show_in_viewport", True)
        obj.hide_viewport = not show_in_viewport
        obj.hide_set(not show_in_viewport)
    
    def _configure_asset(self, asset: Dict) -> None:
        """Configure asset by applying mesh configurations"""
        print(f"[INFO] Configuring asset: {asset['name']}")
        for mesh in asset.get("meshes", []):
            self._configure_mesh_object(mesh)