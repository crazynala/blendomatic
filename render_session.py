"""
Render Session - Core engine for Blender render automation
Separates business logic from UI concerns
"""
import bpy
import json
import os
import math
import datetime as _dt
from pathlib import Path
from typing import List, Dict, Optional, Any

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
from path_utils import (
    RENDER_CONFIG_PATH,
    GARMENTS_DIR,
    FABRICS_DIR,
    RENDERS_DIR,
    DEBUG_DIR,
    resolve_project_path,
)


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
        self.garment_views: List[Dict] = []
        self.render_view: Optional[Dict] = None
        self.render_view_code: Optional[str] = None
        self.fabric: Optional[Dict] = None
        self.asset: Optional[Dict] = None
        self.material: Optional[Any] = None
        
        # Available options (loaded once)
        self.garments = list(GARMENTS_DIR.glob("*.json"))
        self.fabrics = list(FABRICS_DIR.glob("*.json"))
        
        # Status tracking
        self._garment_loaded = False
        self._fabric_applied = False
        self.save_debug_files: bool = True
        self.enable_debug_logging: bool = False

        # Track when this session began so renders share a consistent date folder
        self._batch_started_at = _dt.datetime.now()
        self._batch_date_folder = self._batch_started_at.strftime("%Y-%m-%d")
    
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
            "garment_prefix": self._get_active_view_prefix(),
            "render_view": self.render_view_code,
            "fabric_name": self.fabric["name"] if self.fabric else None,
            "asset_name": self.asset["name"] if self.asset else None,
            "garment_loaded": self._garment_loaded,
            "fabric_applied": self._fabric_applied,
            "ready_to_render": self.is_ready_to_render(),
            "batch_date": self._batch_date_folder,
        }

    def get_batch_date_folder(self) -> str:
        """Return the date folder captured when the session/batch started."""
        return self._batch_date_folder

    def _get_active_view_prefix(self) -> Optional[str]:
        if self.render_view and self.render_view.get("output_prefix"):
            return self.render_view.get("output_prefix")
        if self.garment:
            return self.garment.get("output_prefix")
        return None
    
    def is_ready_to_render(self) -> bool:
        """Check if all required components are set for rendering"""
        return all([
            self.mode,
            self.garment,
            self.render_view,
            self.fabric,
            self.asset,
            self.material,
            self._garment_loaded,
            self._fabric_applied
        ])
    
    # ---------------------------------------------------------
    # Configuration Methods
    # ---------------------------------------------------------
    def set_save_debug_files(self, enabled: bool):
        """Enable or disable saving debug .blend files"""
        self.save_debug_files = enabled
        print(f"[INFO] Save debug files set to: {enabled}")

    def set_enable_debug_logging(self, enabled: bool):
        """Enable or disable verbose debug logging"""
        self.enable_debug_logging = enabled
        print(f"[INFO] Debug logging set to: {enabled}")
    
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
        """Set garment configuration and select its default view"""
        match = next((g for g in self.garments if g.name == garment_name), None)
        if not match:
            available = ", ".join(self.list_garments())
            raise ValueError(f"Unknown garment '{garment_name}'. Available: {available}")

        self.garment = self._load_json(match)
        self.garment_views = self._normalize_garment_views(self.garment)
        if not self.garment_views:
            raise ValueError(f"Garment '{garment_name}' has no valid views configured")

        self.render_view = None
        self.render_view_code = None
        self._garment_loaded = False
        self._fabric_applied = False
        self.asset = None

        # Load the default view immediately so the scene is ready
        default_view_code = self.garment_views[0]["code"]
        self.set_render_view(default_view_code)

        print(f"[INFO] Set garment: {self.garment['name']} (view: {self.render_view_code})")

    def _normalize_garment_views(self, garment: Dict) -> List[Dict]:
        views: List[Dict] = []
        raw_views = garment.get("views")

        fallback_blend = garment.get("blend_file")
        fallback_prefix = garment.get("output_prefix") or garment.get("name") or "garment"

        if isinstance(raw_views, list) and raw_views:
            for view in raw_views:
                if not isinstance(view, dict):
                    continue
                code = (view.get("code") or "").strip()
                blend_file = view.get("blend_file") or fallback_blend
                output_prefix = view.get("output_prefix") or fallback_prefix
                if not code or not blend_file:
                    print(f"[WARN] Skipping invalid view definition on garment '{garment.get('name')}'")
                    continue
                views.append({
                    "code": code,
                    "blend_file": blend_file,
                    "output_prefix": output_prefix
                })

        if not views and fallback_blend:
            views.append({
                "code": garment.get("default_view", "default"),
                "blend_file": fallback_blend,
                "output_prefix": fallback_prefix
            })

        return views

    def set_render_view(self, view_code: Optional[str]) -> None:
        if not self.garment:
            raise RuntimeError("Set a garment before selecting a render view")
        if not self.garment_views:
            self.garment_views = self._normalize_garment_views(self.garment)
        if not self.garment_views:
            raise RuntimeError("Garment has no configured views")

        target_view: Optional[Dict] = None
        if view_code:
            for view in self.garment_views:
                if view.get("code") == view_code:
                    target_view = view
                    break
            if not target_view:
                valid_codes = ", ".join(v.get("code", "?") for v in self.garment_views)
                raise ValueError(f"Unknown view '{view_code}'. Available views: {valid_codes}")
        else:
            target_view = self.garment_views[0]
            view_code = target_view.get("code")

        if not target_view:
            raise RuntimeError("Failed to resolve render view")

        view_already_active = self.render_view_code == view_code and self._garment_loaded

        blend_path = resolve_project_path(target_view.get("blend_file"))
        if not blend_path or not os.path.exists(blend_path):
            raise FileNotFoundError(f"Blend file for view '{view_code}' not found: {target_view.get('blend_file')}")

        need_reload = True
        try:
            current_file = bpy.data.filepath
            if current_file and os.path.exists(current_file):
                try:
                    need_reload = not os.path.samefile(current_file, str(blend_path))
                except Exception:
                    need_reload = (Path(current_file).resolve() != Path(blend_path).resolve())
        except Exception:
            need_reload = True

        if need_reload:
            print(f"[INFO] Loading view '{view_code}' blend file: {blend_path}")
            bpy.ops.wm.open_mainfile(filepath=str(blend_path))
            self._reapply_mode_settings_if_needed()
        elif view_already_active:
            print(f"[INFO] Render view '{view_code}' already active; reusing loaded scene")
            self._reapply_mode_settings_if_needed()
        else:
            print(f"[INFO] Blend file already loaded for view '{view_code}': {blend_path}")

            # Even if the file was already open, make sure the selected render mode is re-applied.
            self._reapply_mode_settings_if_needed()

        self.render_view = target_view
        self.render_view_code = view_code
        self._garment_loaded = True

        if not view_already_active:
            self.asset = None
            self.material = None
            self._fabric_applied = False

    def _reapply_mode_settings_if_needed(self) -> None:
        """Ensure the active render mode settings persist after loading a new blend file."""
        if not self.render_settings:
            return
        try:
            print("[INFO] Re-applying active render mode settings after loading blend file")
            self._apply_render_settings(self.render_settings)
        except Exception as exc:
            print(f"[WARN] Failed to re-apply render settings: {exc}")

    def set_fabric(self, fabric_name: str) -> None:
        """Set fabric and update existing materials"""
        match = next((f for f in self.fabrics if f.name == fabric_name), None)
        if not match:
            available = ", ".join(self.list_fabrics())
            raise ValueError(f"Unknown fabric '{fabric_name}'. Available: {available}")
        
        print(f"[FABRIC] Loading fabric JSON: {match}", flush=True)
        self.fabric = self._load_json(match)
        print(f"[FABRIC] Fabric JSON loaded: {self.fabric.get('name', 'Unknown')}", flush=True)
        
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
        
        # Optionally skip heavy material application for debugging
        import os as _os
        safe_mode = _os.environ.get('BLENDOMATIC_SAFE_MODE') == '1'
        if safe_mode:
            print(f"[FABRIC] SAFE MODE active - skipping material application", flush=True)
            # Pick an existing material as placeholder if available
            try:
                self.material = next((m for m in bpy.data.materials if m), None)
            except Exception:
                self.material = None
        else:
            # Update existing materials in the Blender file with fabric textures
            print(f"[FABRIC] Applying fabric materials...", flush=True)
            self.material = self._apply_fabric_material(self.fabric)
            print(f"[FABRIC] Material application done", flush=True)
            self.debug_material_assignments()
        self.fabric_applied = True
        
        # The materials are already assigned to objects in the Blender file,
        # so we don't need to reassign them - just update their textures
        
        self._fabric_applied = True

        # Apply optional lighting overrides defined on the fabric config
        self._apply_fabric_lighting(self.fabric)

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

        allowed_views = asset.get("render_views")
        if allowed_views:
            if not self.render_view_code:
                raise RuntimeError("Render view must be selected before setting asset with view constraints")
            if self.render_view_code not in allowed_views:
                raise ValueError(
                    f"Asset '{asset_name}' is not configured for view '{self.render_view_code}'. Allowed views: {', '.join(allowed_views)}"
                )
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
        
        if not self.render_view:
            raise RuntimeError("Render view not selected")

        # Generate output path renders/[mode]/[date]/[view_prefix]
        garment_name = self._get_active_view_prefix() or "garment"
        fabric_name = self.fabric.get("suffix", self.fabric["name"].lower().replace(" ", "_"))
        asset_suffix = self.asset.get("suffix", self.asset["name"].lower().replace(" ", "_"))

        date_folder = self.get_batch_date_folder()

        # Ensure mode is set; fallback to 'default' if missing
        mode_name = self.mode or "default"

        outdir = RENDERS_DIR / mode_name / date_folder / garment_name
        outdir.mkdir(parents=True, exist_ok=True)

        filename = f"{garment_name}-{fabric_name}-{asset_suffix}.png"
        outpath = str(outdir / filename)
        print(f"[RENDER] Output directory: {outdir}")
        print(f"[RENDER] Output file: {filename}")
        
        # Render
        bpy.context.scene.render.filepath = outpath
        
        try:
            # Debug render state before rendering
            print("[RENDER] Starting render process - debugging current state:")
            self.debug_render_state()
            
            print(f"[RENDER] Starting render: {filename}")
            
            # Optionally save debug scene before rendering
            if self.save_debug_files:
                mode_folder = self.mode or "default"
                debug_dir = DEBUG_DIR / mode_folder / date_folder
                debug_dir.mkdir(parents=True, exist_ok=True)
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
            if not path:
                print(f"[FABRIC]   ⚠ Empty texture path")
                return None

            resolved = resolve_project_path(path)
            if not resolved or not os.path.exists(resolved):
                print(f"[FABRIC]   ⚠ Texture path does not exist: {path}")
                return None

            abspath = os.path.abspath(str(resolved))
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
    
    def _apply_fabric_lighting(self, fabric: Dict) -> None:
        """Apply optional lighting overrides provided on the fabric config."""
        lighting_config = fabric.get("lighting")
        if not lighting_config:
            print("[LIGHTING] No lighting overrides defined on fabric; skipping", flush=True)
            return

        lights = [obj for obj in bpy.data.objects if obj.type == 'LIGHT']
        if not lights:
            print("[LIGHTING] Lighting overrides requested but no light objects exist in the scene", flush=True)
            return

        print(f"[LIGHTING] Applying lighting overrides: {list(lighting_config.keys())}", flush=True)
        for label, config in lighting_config.items():
            if not isinstance(config, dict):
                print(f"[LIGHTING]   ⚠ Skipping '{label}' (expected dict, got {type(config).__name__})", flush=True)
                continue

            match_name = (config.get("match_name") or label or "").strip()
            if not match_name:
                print(f"[LIGHTING]   ⚠ Skipping '{label}' (missing match_name)", flush=True)
                continue

            match_lower = match_name.lower()
            matched = [obj for obj in lights if match_lower in obj.name.lower()]
            exact = next((obj for obj in lights if obj.name == match_name), None)
            if exact and exact not in matched:
                matched.insert(0, exact)

            if not matched:
                print(f"[LIGHTING]   ⚠ No lights matched '{match_name}'", flush=True)
                continue

            for light_obj in matched:
                light = light_obj.data
                print(f"[LIGHTING]   → Updating light '{light_obj.name}'", flush=True)

                original_energy = getattr(light, "energy", None)
                energy_value = original_energy
                energy_changed = False

                if "power" in config:
                    try:
                        energy_value = float(config["power"])
                        energy_changed = True
                        print(f"[LIGHTING]     power: {original_energy} → {energy_value}", flush=True)
                    except (TypeError, ValueError):
                        print(f"[LIGHTING]     ⚠ Invalid power value: {config['power']}", flush=True)

                if "exposure" in config:
                    try:
                        exposure_factor = math.pow(2.0, float(config["exposure"]))
                        base_energy = energy_value if energy_value is not None else original_energy
                        base_energy = base_energy if base_energy is not None else 0.0
                        energy_value = base_energy * exposure_factor
                        energy_changed = True
                        print(f"[LIGHTING]     exposure: {config['exposure']} (×{exposure_factor:.3f})", flush=True)
                    except (TypeError, ValueError):
                        print(f"[LIGHTING]     ⚠ Invalid exposure value: {config['exposure']}", flush=True)

                if energy_changed and energy_value is not None and (original_energy is None or not math.isclose(original_energy, energy_value, rel_tol=1e-6)):
                    light.energy = energy_value
                    print(f"[LIGHTING]     energy applied: {light.energy}", flush=True)

                color_value = None
                color_source = None
                if "color" in config:
                    color_value = self._parse_color_value(config["color"])
                    color_source = "color"
                    if color_value is None:
                        print(f"[LIGHTING]     ⚠ Invalid color value: {config['color']}", flush=True)

                if color_value is None and "temperature" in config:
                    color_value = self._kelvin_to_rgb(config["temperature"])
                    color_source = "temperature"
                    if color_value is None:
                        print(f"[LIGHTING]     ⚠ Invalid temperature value: {config['temperature']}", flush=True)

                if color_value is not None:
                    light.color = color_value
                    preview = tuple(round(c, 3) for c in color_value)
                    print(f"[LIGHTING]     {color_source} applied: {preview}", flush=True)

        print("[LIGHTING] Lighting overrides applied", flush=True)

    @staticmethod
    def _parse_color_value(value):
        """Parse a color definition (RGB list/tuple or hex string) into a 0-1 tuple."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("#"):
                text = text[1:]
            if len(text) in (6, 8):
                try:
                    r = int(text[0:2], 16) / 255.0
                    g = int(text[2:4], 16) / 255.0
                    b = int(text[4:6], 16) / 255.0
                    return (r, g, b)
                except ValueError:
                    return None

        if isinstance(value, (list, tuple)):
            try:
                comps = [float(v) for v in value[:3]]
            except (TypeError, ValueError):
                return None
            if not comps:
                return None
            while len(comps) < 3:
                comps.append(comps[-1])
            return tuple(max(0.0, min(1.0, c)) for c in comps[:3])

        return None

    @staticmethod
    def _kelvin_to_rgb(kelvin):
        """Approximate conversion from color temperature (Kelvin) to RGB tuple."""
        try:
            temperature = float(kelvin)
        except (TypeError, ValueError):
            return None

        # Clamp to a reasonable range for the formula
        temperature = max(1000.0, min(40000.0, temperature)) / 100.0

        if temperature <= 66:
            red = 255.0
            green = 99.4708025861 * math.log(temperature) - 161.1195681661
            if temperature <= 19:
                blue = 0.0
            else:
                blue = 138.5177312231 * math.log(temperature - 10.0) - 305.0447927307
        else:
            red = 329.698727446 * math.pow(temperature - 60.0, -0.1332047592)
            green = 288.1221695283 * math.pow(temperature - 60.0, -0.0755148492)
            blue = 255.0

        def _clamp(channel: float) -> float:
            return max(0.0, min(255.0, channel))

        red = _clamp(red)
        green = _clamp(green)
        blue = _clamp(blue)

        return (red / 255.0, green / 255.0, blue / 255.0)
    
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
        """Configure asset by applying mesh configurations with partial and wildcard matching.

        Matching rules per JSON entry 'name' (json_match_name):
        - If it ends with '*': match if mesh_object.name startswith(json_match_name without '*').
        - Otherwise: match if json_match_name is a substring of mesh_object.name (case-insensitive).
        - If no config matches a mesh object: default to render=False.
        Logs each mesh object and the config applied.
        """
        print(f"[INFO] Configuring asset: {asset['name']}", flush=True)

        # Verify render engine is Cycles before configuring mesh objects
        render_engine = bpy.context.scene.render.engine
        print(f"[ASSET_CONFIG] Current render engine: {render_engine}", flush=True)
        if render_engine != "CYCLES":
            print(f"[WARN] Render engine is {render_engine}, not CYCLES. Holdout/shadow_catcher may not work.", flush=True)

        mesh_configs = asset.get("meshes", []) or []

        def _pattern_matches(obj_name: str, pattern: str) -> bool:
            pn = (pattern or "").strip()
            if not pn:
                return False
            on = obj_name.lower()
            pn_l = pn.lower()
            if pn_l.endswith('*'):
                return on.startswith(pn_l[:-1])
            return pn_l in on

        # Helper to apply a mesh config directly to an object
        def _apply_to_object(obj, cfg: Dict):
            # Compose a minimal config dict expected by _configure_mesh_object logic
            # but operate directly on obj to avoid name lookup
            print(f"[MESH_APPLY] → Object '{obj.name}' applying config: {cfg}", flush=True)

            # Normalize flags from config (support alternate keys)
            holdout_enabled = bool(cfg.get("holdout", cfg.get("is_holdout", False)))
            shadow_catcher_enabled = bool(cfg.get("shadow_catcher", cfg.get("is_shadow_catcher", False)))

            # Render visibility: if not explicitly provided, presume True when holdout or shadow catcher enabled
            if "render" in cfg:
                render_enabled = bool(cfg.get("render"))
            else:
                render_enabled = True if (holdout_enabled or shadow_catcher_enabled) else True
                if holdout_enabled or shadow_catcher_enabled:
                    print("[MESH_APPLY]   render implied True due to holdout/shadow_catcher", flush=True)
            obj.hide_render = not render_enabled
            print(f"[MESH_APPLY]   render: {render_enabled} (hide_render: {obj.hide_render})", flush=True)

            # Holdout
            if hasattr(obj, 'is_holdout'):
                obj.is_holdout = holdout_enabled
                print(f"[MESH_APPLY]   holdout: {holdout_enabled} (is_holdout: {obj.is_holdout})", flush=True)
            else:
                print(f"[MESH_APPLY]   holdout: {holdout_enabled} (NOT APPLIED - unsupported)", flush=True)

            # Shadow catcher
            if hasattr(obj, 'is_shadow_catcher'):
                obj.is_shadow_catcher = shadow_catcher_enabled
                print(f"[MESH_APPLY]   shadow_catcher: {shadow_catcher_enabled} (is_shadow_catcher: {obj.is_shadow_catcher})", flush=True)
            else:
                print(f"[MESH_APPLY]   shadow_catcher: {shadow_catcher_enabled} (NOT APPLIED - unsupported)", flush=True)

            # Viewport visibility
            show_in_viewport = cfg.get("show_in_viewport", True)
            obj.hide_viewport = not show_in_viewport
            try:
                obj.hide_set(not show_in_viewport)
            except Exception:
                pass
            print(f"[MESH_APPLY]   show_in_viewport: {show_in_viewport} (hide_viewport: {obj.hide_viewport})", flush=True)

        configured_count = 0
        # Iterate through all mesh objects in the scene
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue

            # Find first matching config for this object
            matches = []
            for cfg in mesh_configs:
                name_pat = cfg.get('name', '')
                if _pattern_matches(obj.name, name_pat):
                    matches.append(cfg)

            if matches:
                chosen = matches[0]
                print(f"[ASSET_MATCH] Object '{obj.name}' matched config name='{chosen.get('name')}'", flush=True)
                if len(matches) > 1:
                    print(f"[ASSET_MATCH]   Note: {len(matches)} configs matched; using first.", flush=True)
                _apply_to_object(obj, chosen)
                configured_count += 1
            else:
                # Default behavior: render False when no config found
                default_cfg = {"render": False}
                print(f"[ASSET_MATCH] Object '{obj.name}' no match. Applying default: {default_cfg}", flush=True)
                _apply_to_object(obj, default_cfg)
                configured_count += 1

        print(f"[ASSET_CONFIG] ✅ Asset '{asset['name']}' configured. Objects processed: {configured_count}", flush=True)
    
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