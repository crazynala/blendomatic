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
        """Set fabric and update existing materials"""
        match = next((f for f in self.fabrics if f.name == fabric_name), None)
        if not match:
            available = ", ".join(self.list_fabrics())
            raise ValueError(f"Unknown fabric '{fabric_name}'. Available: {available}")
        
        self.fabric = self._load_json(match)
        
        # Debug: Log the actual loaded fabric config
        print(f"[FABRIC_DEBUG] Current working directory: {os.getcwd()}")
        print(f"[FABRIC_DEBUG] Loading fabric from: {os.path.abspath(match)}")
        print(f"[FABRIC_DEBUG] File exists: {os.path.exists(match)}")
        print(f"[FABRIC_DEBUG] Loaded fabric config from {match}:")
        print(f"[FABRIC_DEBUG] Fabric name: {self.fabric.get('name', 'Unknown')}")
        if 'materials' in self.fabric and 'main_fabric' in self.fabric['materials']:
            main_fabric = self.fabric['materials']['main_fabric']
            if 'hue_sat_params' in main_fabric:
                hue_sat = main_fabric['hue_sat_params']
                print(f"[FABRIC_DEBUG] HUE_SAT params from file: {hue_sat}")
            else:
                print(f"[FABRIC_DEBUG] No hue_sat_params found in main_fabric config")
        else:
            print(f"[FABRIC_DEBUG] No main_fabric config found")
        
        # Update existing materials in the Blender file with fabric textures
        self.material = self._apply_fabric_material(self.fabric)
        self.debug_material_assignments()  # Add this line
        self.fabric_applied = True
        
        # The materials are already assigned to objects in the Blender file,
        # so we don't need to reassign them - just update their textures
        
        self._fabric_applied = True
        print(f"[FABRIC] ✅ Fabric '{self.fabric['name']}' applied to existing materials")
    
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
        # Debug render state before rendering
        print("[RENDER] Starting render process - debugging current state:")
        self.debug_render_state()
        
        if not self.is_ready_to_render():
            missing = []
            if not self.mode: missing.append("mode")
            if not self.garment: missing.append("garment")
            if not self.fabric: missing.append("fabric")
            if not self.asset: missing.append("asset")
            if not self.material: missing.append("material")
            if not self._garment_loaded: missing.append("garment blend file")
            if not self._fabric_applied: missing.append("fabric material")
            
            print(f"[RENDER_ERROR] Missing components for render:")
            for component in missing:
                print(f"[RENDER_ERROR]   - {component}")
            print(f"[RENDER_ERROR] Current state:")
            print(f"[RENDER_ERROR]   mode: {self.mode}")
            print(f"[RENDER_ERROR]   garment: {self.garment.get('name') if self.garment else None}")
            print(f"[RENDER_ERROR]   fabric: {self.fabric.get('name') if self.fabric else None}")
            print(f"[RENDER_ERROR]   asset: {self.asset.get('name') if self.asset else None}")
            print(f"[RENDER_ERROR]   material: {self.material.name if self.material else None}")
            print(f"[RENDER_ERROR]   garment_loaded: {self._garment_loaded}")
            print(f"[RENDER_ERROR]   fabric_applied: {self._fabric_applied}")
            
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
        
        try:
            # Debug render state before rendering
            print("[RENDER] Starting render process - debugging current state:")
            self.debug_render_state()
            
            print(f"[RENDER] Starting render: {filename}")
            
            # Save debug scene before rendering
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            debug_path = debug_dir / f"debug_scene_{fabric_name}_{asset_suffix}.blend"
            bpy.ops.wm.save_mainfile(filepath=str(debug_path))
            print(f"[DEBUG] Saved debug scene to {debug_path}")
            
            bpy.ops.render.render(write_still=True)
            print(f"[RENDER] Completed: {outpath}")
            
        except Exception as e:
            print(f"[RENDER_ERROR] Render failed: {e}")
            raise
        
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
        """Update existing materials in the Blender file with fabric textures and parameters."""
        print(f"[FABRIC] Applying fabric '{fabric['name']}' to existing materials")

        # Support new multi-material structure or legacy single material structure
        materials_config = fabric.get("materials", {})
        if not materials_config:
            # Legacy format - convert to new format
            materials_config = {
                "default": {
                    "match_name": "",  # Empty match means apply to all materials
                    "textures": fabric.get("textures", {}),
                    "material_params": fabric.get("material_params", {}),
                    "hue_sat_params": {}
                }
            }

        print(f"[FABRIC] Material configurations: {list(materials_config.keys())}")
        
        for config_name, config in materials_config.items():
            print(f"[FABRIC] Processing config '{config_name}': {config}")
            
            match_name = config.get("match_name", "").lower()
            textures = config.get("textures", {}) or {}
            material_params = config.get("material_params", {}) or {}
            hue_sat_params = config.get("hue_sat_params", {}) or {}

            print(f"[FABRIC] Config '{config_name}' - Match: '{match_name}', Textures: {list(textures.keys())}, Params: {material_params}")
            if hue_sat_params:
                print(f"[FABRIC] Config '{config_name}' - HUE_SAT params: {hue_sat_params}")

        materials_updated = []

        def load_or_get_image(path: str):
            """Load an image once, reuse if already loaded with same filepath."""
            if not path or not os.path.exists(path):
                print(f"[FABRIC]   ⚠ Texture path does not exist: {path}")
                return None

            abspath = os.path.abspath(path)
            # Try to find an existing image with same filepath
            for img in bpy.data.images:
                try:
                    if os.path.abspath(bpy.path.abspath(img.filepath)) == abspath:
                        print(f"[FABRIC]   Reusing already loaded image: {img.name}")
                        return img
                except Exception:
                    continue

            print(f"[FABRIC]   Loading image from disk: {abspath}")
            return bpy.data.images.load(abspath)

        def find_principled_bsdf(nodes):
            """Find a Principled BSDF node by name or by type."""
            bsdf = nodes.get("Principled BSDF")
            if bsdf and bsdf.type == 'BSDF_PRINCIPLED':
                return bsdf
            for n in nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    return n
            return None

        def update_socket_texture(socket, tex_key: str, textures_dict: dict):
            """Follow a socket link and set the image on the source TEX_IMAGE node if present."""
            if tex_key not in textures_dict:
                return

            tex_path = textures_dict[tex_key]
            if not socket.links:
                print(f"[FABRIC]     No links on socket '{socket.name}' for texture '{tex_key}'")
                return

            from_node = socket.links[0].from_node
            if from_node.type == 'TEX_IMAGE':
                img = load_or_get_image(tex_path)
                if img:
                    from_node.image = img
                    print(f"[FABRIC]     Socket '{socket.name}' → node '{from_node.name}' set to '{tex_key}'")
            elif from_node.type == 'HUE_SAT':
                # Navigate to the Color socket of the HUE_SAT node
                print(f"[FABRIC]     Found HUE_SAT node '{from_node.name}' on socket '{socket.name}'")
                if "Color" in from_node.inputs and from_node.inputs["Color"].links:
                    color_from_node = from_node.inputs["Color"].links[0].from_node
                    if color_from_node.type == 'TEX_IMAGE':
                        img = load_or_get_image(tex_path)
                        if img:
                            color_from_node.image = img
                            print(f"[FABRIC]     HUE_SAT '{from_node.name}' → TEX_IMAGE '{color_from_node.name}' set to '{tex_key}'")
                    else:
                        print(f"[FABRIC]     HUE_SAT Color input not linked to TEX_IMAGE: {color_from_node.type}")
                else:
                    print(f"[FABRIC]     HUE_SAT node has no Color input or no links")
            else:
                print(f"[FABRIC]     Linked node for socket '{socket.name}' is not TEX_IMAGE or HUE_SAT: {from_node.type} ({from_node.name})")

        def update_hue_sat_node(socket, hue_sat_params_dict: dict):
            """Update HUE_SAT node parameters if found on the socket."""
            if not socket.links or not hue_sat_params_dict:
                return
            
            from_node = socket.links[0].from_node
            if from_node.type == 'HUE_SAT':
                print(f"[FABRIC]     Updating HUE_SAT node '{from_node.name}' on socket '{socket.name}'")
                
                # Update HUE_SAT parameters
                if "hue" in hue_sat_params_dict:
                    from_node.inputs["Hue"].default_value = hue_sat_params_dict["hue"]
                    print(f"[FABRIC]       Set Hue: {hue_sat_params_dict['hue']}")
                
                if "saturation" in hue_sat_params_dict:
                    from_node.inputs["Saturation"].default_value = hue_sat_params_dict["saturation"]
                    print(f"[FABRIC]       Set Saturation: {hue_sat_params_dict['saturation']}")
                
                if "value" in hue_sat_params_dict:
                    from_node.inputs["Value"].default_value = hue_sat_params_dict["value"]
                    print(f"[FABRIC]       Set Value: {hue_sat_params_dict['value']}")
                
                if "fac" in hue_sat_params_dict:
                    from_node.inputs["Fac"].default_value = hue_sat_params_dict["fac"]
                    print(f"[FABRIC]       Set Fac: {hue_sat_params_dict['fac']}")
        
        def should_apply_numeric_value(socket):
            """Check if we should apply a numeric value (socket not connected to other nodes)."""
            return not socket.links

        def find_material_output(nodes):
            """Find the main Material Output node."""
            for n in nodes:
                if n.type == 'OUTPUT_MATERIAL':
                    return n
            return None

        # Process all materials and match them to configs
        for mat in bpy.data.materials:
            if not mat.use_nodes:
                print(f"[FABRIC] Skipping material '{mat.name}' - no node tree")
                continue

            print(f"[FABRIC] Checking material: {mat.name}")
            
            # Find which config applies to this material
            matching_config = None
            for config_name, config in materials_config.items():
                match_name = config.get("match_name", "").lower()
                if not match_name:  # Empty match_name matches all materials
                    matching_config = (config_name, config)
                    print(f"[FABRIC] Material '{mat.name}' matches config '{config_name}' (empty match_name)")
                    break
                elif match_name in mat.name.lower():
                    matching_config = (config_name, config)
                    print(f"[FABRIC] Material '{mat.name}' matches config '{config_name}' (contains '{match_name}')")
                    break
            
            if not matching_config:
                print(f"[FABRIC] ❌ No matching config for material '{mat.name}' - available configs: {list(materials_config.keys())}")
                continue
                
            config_name, config = matching_config
            textures = config.get("textures", {}) or {}
            material_params = config.get("material_params", {}) or {}
            hue_sat_params = config.get("hue_sat_params", {}) or {}

            print(f"[FABRIC] ✅ Applying config '{config_name}' to material '{mat.name}'")
            
            nodes = mat.node_tree.nodes

            bsdf = find_principled_bsdf(nodes)
            if not bsdf:
                print(f"[FABRIC]   No Principled BSDF found in '{mat.name}', skipping")
                continue

            # --- NUMERIC PARAMS (stitch-style materials or overrides) ---
            # Base color (expects RGBA list or tuple)
            if "base_color" in material_params:
                if should_apply_numeric_value(bsdf.inputs["Base Color"]):
                    try:
                        bc = material_params["base_color"]
                        # Ensure 4 components
                        if len(bc) == 3:
                            bc = list(bc) + [1.0]
                        bsdf.inputs["Base Color"].default_value = bc
                        print(f"[FABRIC]   Set Base Color: {bc}")
                    except Exception as e:
                        print(f"[FABRIC]   ⚠ Failed to set Base Color: {e}")
                else:
                    print(f"[FABRIC]   Skipping Base Color (socket connected)")

            if "metallic" in material_params and should_apply_numeric_value(bsdf.inputs["Metallic"]):
                bsdf.inputs["Metallic"].default_value = material_params["metallic"]
                print(f"[FABRIC]   Set Metallic: {material_params['metallic']}")
            elif "metallic" in material_params:
                print(f"[FABRIC]   Skipping Metallic (socket connected)")

            if "roughness" in material_params and should_apply_numeric_value(bsdf.inputs["Roughness"]):
                bsdf.inputs["Roughness"].default_value = material_params["roughness"]
                print(f"[FABRIC]   Set Roughness: {material_params['roughness']}")
            elif "roughness" in material_params:
                print(f"[FABRIC]   Skipping Roughness (socket connected)")

            if "ior" in material_params:
                try:
                    bsdf.inputs["IOR"].default_value = material_params["ior"]
                    print(f"[FABRIC]   Set IOR: {material_params['ior']}")
                except Exception as e:
                    print(f"[FABRIC]   ⚠ Failed to set IOR: {e}")

            if "alpha" in material_params and should_apply_numeric_value(bsdf.inputs["Alpha"]):
                bsdf.inputs["Alpha"].default_value = material_params["alpha"]
                print(f"[FABRIC]   Set Alpha: {material_params['alpha']}")
            elif "alpha" in material_params:
                print(f"[FABRIC]   Skipping Alpha (socket connected)")

            # --- TEXTURE-DRIVEN PARAMS (fabric materials with linked nodes) ---
            # Map JSON texture keys to BSDF sockets
            bsdf_socket_map = {
                "base_color": "Base Color",
                "roughness": "Roughness", 
                "metallic": "Metallic",
                "alpha": "Alpha",
                "normal": "Normal",
            }

            for tex_key, socket_name in bsdf_socket_map.items():
                if tex_key not in textures:
                    continue
                if socket_name not in bsdf.inputs:
                    print(f"[FABRIC]   BSDF has no socket '{socket_name}'")
                    continue

                socket = bsdf.inputs[socket_name]
                update_socket_texture(socket, tex_key, textures)
                
                # Also update HUE_SAT parameters if present
                update_hue_sat_node(socket, hue_sat_params)

            # Displacement is usually on the Material Output
            if "displacement" in textures:
                out = find_material_output(nodes)
                if out and "Displacement" in out.inputs:
                    update_socket_texture(out.inputs["Displacement"], "displacement", textures)

            materials_updated.append(mat.name)

        print(f"[FABRIC] Updated {len(materials_updated)} materials: {materials_updated}")
        return bpy.data.materials[materials_updated[0]] if materials_updated else None
    
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
        
        # Debug available object properties for holdout/shadow_catcher
        relevant_props = [attr for attr in dir(obj) if attr in ['is_holdout', 'is_shadow_catcher', 'hide_render', 'hide_viewport']]
        print(f"[MESH_CONFIG]   available relevant properties: {relevant_props}", flush=True)
        
        # Also show cycles properties if available
        if hasattr(obj, 'cycles'):
            cycles_props = [attr for attr in dir(obj.cycles) if not attr.startswith('_')]
            print(f"[MESH_CONFIG]   available cycles properties: {cycles_props}", flush=True)
        
        # Holdout configuration
        holdout_enabled = mesh_config.get("holdout", False)
        if hasattr(obj, 'is_holdout'):
            obj.is_holdout = holdout_enabled
            print(f"[MESH_CONFIG]   holdout: {holdout_enabled} (is_holdout: {obj.is_holdout})", flush=True)
        else:
            print(f"[WARN] Object {obj.name} doesn't support is_holdout property", flush=True)
            print(f"[MESH_CONFIG]   holdout: {holdout_enabled} (NOT APPLIED - unsupported)", flush=True)
        
        # Shadow catcher configuration
        shadow_catcher_enabled = mesh_config.get("shadow_catcher", False)
        if hasattr(obj, 'is_shadow_catcher'):
            obj.is_shadow_catcher = shadow_catcher_enabled
            print(f"[MESH_CONFIG]   shadow_catcher: {shadow_catcher_enabled} (is_shadow_catcher: {obj.is_shadow_catcher})", flush=True)
        else:
            print(f"[WARN] Object {obj.name} doesn't support is_shadow_catcher property", flush=True)
            print(f"[MESH_CONFIG]   shadow_catcher: {shadow_catcher_enabled} (NOT APPLIED - unsupported)", flush=True)
        
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
    
    def debug_material_assignments(self):
        """Debug which materials are assigned to which objects"""
        print(f"[DEBUG] Material assignments in scene:")
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and not obj.hide_render:
                print(f"[DEBUG]   Object '{obj.name}' (visible={not obj.hide_render}):")
                if obj.data.materials:
                    for i, mat in enumerate(obj.data.materials):
                        if mat:
                            print(f"[DEBUG]     Material slot {i}: {mat.name}")
                        else:
                            print(f"[DEBUG]     Material slot {i}: <empty>")
                else:
                    print(f"[DEBUG]     No materials assigned")

    def debug_render_state(self):
        """Debug the state right before rendering"""
        print(f"[DEBUG_RENDER] Pre-render state check:")
        
        # Check if textures are actually loaded and valid
        print(f"[DEBUG_RENDER] Loaded images in scene:")
        for img in bpy.data.images:
            if img.filepath:
                exists = os.path.exists(bpy.path.abspath(img.filepath))
                print(f"[DEBUG_RENDER]   {img.name}: {img.filepath} (exists: {exists}, size: {img.size[0]}x{img.size[1]})")
        
        # Check material nodes for the main fabric materials  
        print(f"[DEBUG_RENDER] Main fabric material node states:")
        for mat_name in ['fabric', 'fabric.001', 'fabric.002']:
            mat = bpy.data.materials.get(mat_name)
            if mat and mat.use_nodes:
                print(f"[DEBUG_RENDER]   Material '{mat_name}':")
                bsdf = None
                for node in mat.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        bsdf = node
                        break
                
                if bsdf:
                    # Check Base Color connection
                    base_color_socket = bsdf.inputs["Base Color"]
                    if base_color_socket.links:
                        from_node = base_color_socket.links[0].from_node
                        print(f"[DEBUG_RENDER]     Base Color linked to: {from_node.type} ({from_node.name})")
                        if from_node.type == 'HUE_SAT':
                            print(f"[DEBUG_RENDER]       HUE_SAT settings - Hue: {from_node.inputs['Hue'].default_value}, Sat: {from_node.inputs['Saturation'].default_value}, Val: {from_node.inputs['Value'].default_value}, Fac: {from_node.inputs['Fac'].default_value}")
                            if from_node.inputs["Color"].links:
                                tex_node = from_node.inputs["Color"].links[0].from_node
                                if tex_node.type == 'TEX_IMAGE':
                                    img = tex_node.image
                                    print(f"[DEBUG_RENDER]       Texture: {img.name if img else 'None'} ({img.filepath if img else 'No path'})")
                    else:
                        print(f"[DEBUG_RENDER]     Base Color: {base_color_socket.default_value}")
        
        # Check lighting configuration
        print(f"[DEBUG_RENDER] Lighting configuration:")
        try:
            scene = bpy.context.scene
            world = scene.world
            
            if world:
                print(f"[DEBUG_RENDER]   World material: {world.name}")
                if world.use_nodes:
                    print(f"[DEBUG_RENDER]   World uses nodes: True")
                    # Check for background shader and its settings
                    for node in world.node_tree.nodes:
                        if node.type == 'BACKGROUND':
                            print(f"[DEBUG_RENDER]     Background node found: {node.name}")
                            color_input = node.inputs.get("Color")
                            strength_input = node.inputs.get("Strength")
                            if color_input:
                                if color_input.links:
                                    from_node = color_input.links[0].from_node
                                    print(f"[DEBUG_RENDER]       Color linked to: {from_node.type} ({from_node.name})")
                                    if from_node.type == 'TEX_ENVIRONMENT':
                                        img = from_node.image
                                        print(f"[DEBUG_RENDER]         Environment texture: {img.name if img else 'None'} ({img.filepath if img else 'No path'})")
                                        if img:
                                            abspath = bpy.path.abspath(img.filepath)
                                            try:
                                                exists = os.path.exists(abspath)
                                                file_bytes = os.path.getsize(abspath) if exists else -1
                                            except Exception:
                                                exists = False
                                                file_bytes = -1
                                            # Basic Blender image metadata
                                            src = getattr(img, "source", "N/A")
                                            fmt = getattr(img, "file_format", "N/A")
                                            cs = getattr(img, "colorspace_settings", None)
                                            cs_name = cs.name if cs else "N/A"
                                            has_data = getattr(img, "has_data", None)
                                            # sample first pixel if available
                                            sample_color = None
                                            try:
                                                if hasattr(img, "pixels") and len(img.pixels) >= 4:
                                                    sample_color = (img.pixels[0], img.pixels[1], img.pixels[2])
                                            except Exception:
                                                sample_color = None

                                            print(f"[DEBUG_RENDER]         Texture exists: {exists}, on-disk bytes: {file_bytes}, image.size: {img.size[0]}x{img.size[1]}")
                                            print(f"[DEBUG_RENDER]         Image source: {src}, file_format: {fmt}, colorspace: {cs_name}, has_data: {has_data}")
                                            if sample_color:
                                                print(f"[DEBUG_RENDER]         First pixel sample (R,G,B): {sample_color}")
                                            else:
                                                print(f"[DEBUG_RENDER]         No pixel sample available (image.pixels length: {len(img.pixels) if hasattr(img, 'pixels') else 'N/A'})")
                            if strength_input:
                                print(f"[DEBUG_RENDER]       Strength: {strength_input.default_value}")
                else:
                    print(f"[DEBUG_RENDER]   World uses nodes: False")
                    print(f"[DEBUG_RENDER]   World color: {world.color}")
            else:
                print(f"[DEBUG_RENDER]   No world material found")
        except Exception as e:
            print(f"[DEBUG_RENDER]   Error checking world lighting: {e}")
        
        # Check light objects in scene
        lights = [obj for obj in bpy.data.objects if obj.type == 'LIGHT']
        print(f"[DEBUG_RENDER]   Light objects in scene: {len(lights)}")
        for light_obj in lights:
            light = light_obj.data
            print(f"[DEBUG_RENDER]     Light '{light_obj.name}': type={light.type}, energy={light.energy}, color={light.color}, visible={not light_obj.hide_render}")
            if hasattr(light, 'size'):
                print(f"[DEBUG_RENDER]       Size: {light.size}")
            if hasattr(light, 'angle') and light.type == 'SPOT':
                print(f"[DEBUG_RENDER]       Spot angle: {light.angle}")
        
        # Check render settings that might affect lighting
        print(f"[DEBUG_RENDER] Render settings:")
        print(f"[DEBUG_RENDER]   Engine: {scene.render.engine}")
        if scene.render.engine == 'CYCLES':
            print(f"[DEBUG_RENDER]   Samples: {scene.cycles.samples}")
            print(f"[DEBUG_RENDER]   Max bounces: {scene.cycles.max_bounces}")
            print(f"[DEBUG_RENDER]   Diffuse bounces: {scene.cycles.diffuse_bounces}")
            print(f"[DEBUG_RENDER]   Glossy bounces: {scene.cycles.glossy_bounces}")
            print(f"[DEBUG_RENDER]   Transmission bounces: {scene.cycles.transmission_bounces}")
            print(f"[DEBUG_RENDER]   Volume bounces: {scene.cycles.volume_bounces}")
            print(f"[DEBUG_RENDER]   Transparent bounces: {scene.cycles.transparent_max_bounces}")
        
        # Check color management
        print(f"[DEBUG_RENDER] Color management:")
        color_mgmt = scene.view_settings
        print(f"[DEBUG_RENDER]   View transform: {color_mgmt.view_transform}")
        print(f"[DEBUG_RENDER]   Look: {color_mgmt.look}")
        print(f"[DEBUG_RENDER]   Exposure: {color_mgmt.exposure}")
        print(f"[DEBUG_RENDER]   Gamma: {color_mgmt.gamma}")
        
        seq_editor = scene.sequence_editor_color_space if hasattr(scene, 'sequence_editor_color_space') else 'N/A'
        display_device = scene.display_settings.display_device if hasattr(scene, 'display_settings') else 'N/A'
        print(f"[DEBUG_RENDER]   Display device: {display_device}")
        print(f"[DEBUG_RENDER]   Sequencer color space: {seq_editor}")