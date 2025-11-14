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
        
        import sys
        print(f"[SET_MODE] Setting mode to: {mode_name}", flush=True)
        sys.stdout.flush()
        print(f"[SET_MODE] Available modes: {list(self.render_cfg['modes'].keys())}", flush=True)
        sys.stdout.flush()
        
        self.mode = mode_name
        self.render_settings = self.render_cfg["modes"][mode_name]
        
        print(f"[SET_MODE] Loaded render settings for '{mode_name}': {self.render_settings}", flush=True)
        sys.stdout.flush()
        
        self._apply_render_settings(self.render_settings)
        print(f"[SET_MODE] ✅ Mode '{mode_name}' set and applied successfully", flush=True)
        sys.stdout.flush()
    
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
        
        import sys
        print(f"[RENDER_SETTINGS] Starting to apply render settings from config: {config}", flush=True)
        sys.stdout.flush()
        
        # Engine
        old_engine = scene.render.engine
        new_engine = config.get("engine", "CYCLES")
        scene.render.engine = new_engine
        print(f"[RENDER_SETTINGS] Engine: {old_engine} → {new_engine}", flush=True)
        sys.stdout.flush()
        
        # Resolution
        res = config.get("resolution", {})
        old_res_x = scene.render.resolution_x
        old_res_y = scene.render.resolution_y
        old_scale = scene.render.resolution_percentage
        
        scene.render.resolution_x = res.get("x", 1920)
        scene.render.resolution_y = res.get("y", 1080)
        scene.render.resolution_percentage = res.get("scale", 100)
        
        print(f"[RENDER_SETTINGS] Resolution: {old_res_x}x{old_res_y}@{old_scale}% → {scene.render.resolution_x}x{scene.render.resolution_y}@{scene.render.resolution_percentage}%", flush=True)
        
        # Samples
        if scene.render.engine == "CYCLES":
            old_samples = getattr(scene.cycles, 'samples', 'N/A')
            old_adaptive = getattr(scene.cycles, 'use_adaptive_sampling', 'N/A')
            old_device = getattr(scene.cycles, 'device', 'N/A')
            old_preview = getattr(scene.cycles, 'preview_samples', 'N/A')
            
            # Set all sample-related settings
            target_samples = config.get("samples", 16)
            scene.cycles.samples = target_samples
            scene.cycles.use_adaptive_sampling = config.get("adaptive_sampling", True)
            scene.cycles.device = config.get("device", "GPU")
            scene.cycles.preview_samples = config.get("preview_samples", 4)
            
            # Force disable adaptive sampling for very low sample counts
            if target_samples <= 16:
                scene.cycles.use_adaptive_sampling = False
                print(f"[RENDER_SETTINGS] Disabling adaptive sampling for fast render ({target_samples} samples)", flush=True)
            
            # Also set adaptive threshold if adaptive sampling is enabled
            if scene.cycles.use_adaptive_sampling:
                scene.cycles.adaptive_threshold = config.get("adaptive_threshold", 0.01)
                print(f"[RENDER_SETTINGS] Adaptive threshold: {scene.cycles.adaptive_threshold}", flush=True)
            
            print(f"[RENDER_SETTINGS] Samples: {old_samples} → {scene.cycles.samples}", flush=True)
            print(f"[RENDER_SETTINGS] Adaptive sampling: {old_adaptive} → {scene.cycles.use_adaptive_sampling}", flush=True)
            print(f"[RENDER_SETTINGS] Device: {old_device} → {scene.cycles.device}", flush=True)
            print(f"[RENDER_SETTINGS] Preview samples: {old_preview} → {scene.cycles.preview_samples}", flush=True)
            
            # Double-check the values after setting them
            print(f"[RENDER_SETTINGS] VERIFICATION - Final samples: {scene.cycles.samples}", flush=True)
            print(f"[RENDER_SETTINGS] VERIFICATION - Final adaptive: {scene.cycles.use_adaptive_sampling}", flush=True)
        
        # Output format
        old_format = scene.render.image_settings.file_format
        fmt = config.get("output_format", "PNG").upper()
        scene.render.image_settings.file_format = fmt
        print(f"[RENDER_SETTINGS] Output format: {old_format} → {fmt}", flush=True)
        
        print(f"[RENDER_SETTINGS] ✅ All render settings applied successfully", flush=True)
    
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
            print(f"[WARN] Mesh object not found: {mesh_config['name']}", flush=True)
            return
        
        # Log configuration being applied
        print(f"[MESH_CONFIG] Configuring mesh: {mesh_config['name']}", flush=True)
        
        # Rendering visibility
        render_enabled = mesh_config.get("render", True)
        obj.hide_render = not render_enabled
        print(f"[MESH_CONFIG]   render: {render_enabled} (hide_render: {obj.hide_render})", flush=True)
        
        # Check render engine and Blender version
        render_engine = bpy.context.scene.render.engine
        blender_version = bpy.app.version_string
        print(f"[MESH_CONFIG]   render_engine: {render_engine}, blender_version: {blender_version}", flush=True)
        
        # Debug available cycles properties
        if hasattr(obj, 'cycles'):
            available_props = [attr for attr in dir(obj.cycles) if not attr.startswith('_')]
            print(f"[MESH_CONFIG]   available cycles properties: {available_props}", flush=True)
        
        # Holdout configuration
        holdout_enabled = mesh_config.get("holdout", False)
        if hasattr(obj, 'cycles') and hasattr(obj.cycles, 'is_holdout'):
            obj.cycles.is_holdout = holdout_enabled
            print(f"[MESH_CONFIG]   holdout: {holdout_enabled} (is_holdout: {obj.cycles.is_holdout})", flush=True)
        elif hasattr(obj, 'cycles'):
            print(f"[WARN] Object {obj.name} cycles properties don't support is_holdout (Blender version issue?)", flush=True)
            print(f"[MESH_CONFIG]   holdout: {holdout_enabled} (NOT APPLIED - unsupported)", flush=True)
        else:
            print(f"[WARN] Object {obj.name} has no cycles properties - render engine issue?", flush=True)
        
        # Shadow catcher configuration
        shadow_catcher_enabled = mesh_config.get("shadow_catcher", False)
        if hasattr(obj, 'is_shadow_catcher'):
            obj.is_shadow_catcher = shadow_catcher_enabled
            print(f"[MESH_CONFIG]   shadow_catcher: {shadow_catcher_enabled} (is_shadow_catcher: {obj.is_shadow_catcher})", flush=True)
        elif hasattr(obj, 'cycles'):
            print(f"[WARN] Object {obj.name} cycles properties don't support is_shadow_catcher (Blender version issue?)", flush=True)
            print(f"[MESH_CONFIG]   shadow_catcher: {shadow_catcher_enabled} (NOT APPLIED - unsupported)", flush=True)
        else:
            print(f"[WARN] Object {obj.name} has no cycles properties for shadow_catcher - render engine issue?", flush=True)
        
        # Viewport visibility
        show_in_viewport = mesh_config.get("show_in_viewport", True)
        obj.hide_viewport = not show_in_viewport
        obj.hide_set(not show_in_viewport)
        print(f"[MESH_CONFIG]   show_in_viewport: {show_in_viewport} (hide_viewport: {obj.hide_viewport})", flush=True)
        
        print(f"[MESH_CONFIG] ✅ {mesh_config['name']} configured successfully", flush=True)
    
    def _configure_asset(self, asset: Dict) -> None:
        """Configure asset by applying mesh configurations"""
        print(f"[INFO] Configuring asset: {asset['name']}", flush=True)
        
        # Verify render engine is Cycles before configuring mesh objects
        render_engine = bpy.context.scene.render.engine
        print(f"[ASSET_CONFIG] Current render engine: {render_engine}", flush=True)
        if render_engine != "CYCLES":
            print(f"[WARN] Render engine is {render_engine}, not CYCLES. Holdout/shadow_catcher may not work.", flush=True)
        
        for mesh in asset.get("meshes", []):
            self._configure_mesh_object(mesh)
        
        print(f"[ASSET_CONFIG] ✅ Asset '{asset['name']}' configured with {len(asset.get('meshes', []))} meshes", flush=True)