"""
Demo/Test version of RenderSession for development without Blender
This mock version simulates the behavior for testing UI interfaces
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
import time

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
from path_utils import (
    RENDER_CONFIG_PATH,
    GARMENTS_DIR,
    FABRICS_DIR,
    RENDERS_DIR,
)


class MockRenderSession:
    """
    Mock version of RenderSession for testing without Blender
    Simulates all the functionality for UI development
    """
    
    def __init__(self):
        print("[DEMO MODE] Initializing mock render session...")
        
        # Load real config if available, otherwise use mock data
        if os.path.exists(RENDER_CONFIG_PATH):
            self.render_cfg = self._load_json(RENDER_CONFIG_PATH)
        else:
            self.render_cfg = self._mock_render_config()
        
        # Current selections
        self.mode: Optional[str] = None
        self.render_settings: Optional[Dict] = None
        self.garment: Optional[Dict] = None
        self.garment_views: List[Dict] = []
        self.render_view: Optional[Dict] = None
        self.render_view_code: Optional[str] = None
        self.fabric: Optional[Dict] = None
        self.asset: Optional[Dict] = None
        self.material: Optional[str] = None
        
        # Available options
        if GARMENTS_DIR.exists():
            self.garments = list(GARMENTS_DIR.glob("*.json"))
        else:
            self.garments = [Path("mock_garment.json")]
            
        if FABRICS_DIR.exists():
            self.fabrics = list(FABRICS_DIR.glob("*.json"))
        else:
            self.fabrics = [Path("mock_fabric.json")]
        
        # Status tracking
        self._garment_loaded = False
        self._fabric_applied = False
        
        print("[DEMO MODE] Mock session ready!")
    
    def _mock_render_config(self):
        """Mock render configuration"""
        return {
            "modes": {
                "fast": {"engine": "CYCLES", "samples": 4, "resolution": {"x": 640, "y": 360}},
                "prod": {"engine": "CYCLES", "samples": 256, "resolution": {"x": 1920, "y": 1080}},
                "preview": {"engine": "EEVEE", "samples": 16, "resolution": {"x": 1280, "y": 720}}
            }
        }
    
    def _load_json(self, path: Path) -> Dict:
        """Load JSON file with error handling"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"[DEMO] Mock data for {path}")
            if "garment" in str(path):
                return {"name": "Mock Garment", "assets": [{"name": "Mock Asset"}]}
            elif "fabric" in str(path):
                return {"name": "Mock Fabric"}
            return {}
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {e}")
    
    # ---------------------------------------------------------
    # State Query Methods (same interface as real RenderSession)
    # ---------------------------------------------------------
    
    def list_modes(self) -> List[str]:
        return list(self.render_cfg["modes"].keys())
    
    def list_garments(self) -> List[str]:
        return [g.name for g in self.garments]
    
    def list_fabrics(self) -> List[str]:
        return [f.name for f in self.fabrics]
    
    def list_assets(self) -> List[str]:
        if not self.garment:
            return []
        return [a["name"] for a in self.garment.get("assets", [])]
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "garment_name": self.garment.get("name") if self.garment else None,
            "garment_prefix": self._active_view_prefix(),
            "render_view": self.render_view_code,
            "fabric_name": self.fabric["name"] if self.fabric else None,
            "asset_name": self.asset["name"] if self.asset else None,
            "garment_loaded": self._garment_loaded,
            "fabric_applied": self._fabric_applied,
            "ready_to_render": self.is_ready_to_render()
        }

    def _active_view_prefix(self) -> Optional[str]:
        if self.render_view and self.render_view.get("output_prefix"):
            return self.render_view.get("output_prefix")
        if self.garment:
            return self.garment.get("output_prefix", "mock")
        return None
    
    def is_ready_to_render(self) -> bool:
        return all([
            self.mode,
            self.garment,
            self.render_view,
            self.fabric,
            self.asset,
            self._garment_loaded,
            self._fabric_applied
        ])
    
    # ---------------------------------------------------------
    # Configuration Methods (mock implementations)
    # ---------------------------------------------------------
    
    def set_mode(self, mode_name: str) -> None:
        if mode_name not in self.render_cfg["modes"]:
            available = ", ".join(self.list_modes())
            raise ValueError(f"Unknown mode '{mode_name}'. Available: {available}")
        
        self.mode = mode_name
        self.render_settings = self.render_cfg["modes"][mode_name]
        print(f"[DEMO] Set render mode: {mode_name}")
        time.sleep(0.1)  # Simulate processing time
    
    def set_garment(self, garment_name: str) -> None:
        match = next((g for g in self.garments if g.name == garment_name), None)
        if not match:
            available = ", ".join(self.list_garments())
            raise ValueError(f"Unknown garment '{garment_name}'. Available: {available}")
        
        self.garment = self._load_json(match)
        self.garment_views = self._normalize_garment_views(self.garment)
        self.render_view = None
        self.render_view_code = None
        
        print(f"[DEMO] Loading garment blend file... (simulated)")
        time.sleep(1)  # Simulate blend file loading
        
        # Reset dependent state
        self.asset = None
        self._garment_loaded = True
        self._fabric_applied = False

        # Activate default view immediately
        self.set_render_view(None)
        
        print(f"[DEMO] Set garment: {self.garment.get('name', garment_name)}")

    def _normalize_garment_views(self, garment: Dict) -> List[Dict]:
        views: List[Dict] = []
        fallback_blend = garment.get("blend_file")
        fallback_prefix = garment.get("output_prefix") or garment.get("name") or "mock"
        raw_views = garment.get("views")

        if isinstance(raw_views, list) and raw_views:
            for view in raw_views:
                if not isinstance(view, dict):
                    continue
                code = (view.get("code") or "").strip()
                blend_file = view.get("blend_file") or fallback_blend
                output_prefix = view.get("output_prefix") or fallback_prefix
                if not code or not blend_file:
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
            raise RuntimeError("Select a garment before choosing a view")
        if not self.garment_views:
            self.garment_views = self._normalize_garment_views(self.garment)
        if not self.garment_views:
            raise RuntimeError("Garment has no views configured")

        target = None
        if view_code:
            for view in self.garment_views:
                if view.get("code") == view_code:
                    target = view
                    break
            if not target:
                valid = ", ".join(v.get("code", "?") for v in self.garment_views)
                raise ValueError(f"Unknown view '{view_code}'. Available: {valid}")
        else:
            target = self.garment_views[0]

        self.render_view = target
        self.render_view_code = target.get("code")
        self._garment_loaded = True
        self.asset = None
        self._fabric_applied = False
    
    def set_fabric(self, fabric_name: str) -> None:
        match = next((f for f in self.fabrics if f.name == fabric_name), None)
        if not match:
            available = ", ".join(self.list_fabrics())
            raise ValueError(f"Unknown fabric '{fabric_name}'. Available: {available}")
        
        self.fabric = self._load_json(match)
        self.material = f"MOCK_MAT_{self.fabric.get('name', fabric_name)}"
        
        time.sleep(0.3)  # Simulate material application
        self._fabric_applied = True
        print(f"[DEMO] Set fabric: {self.fabric.get('name', fabric_name)}")
    
    def set_asset(self, asset_name: str) -> None:
        if not self.garment:
            raise RuntimeError("Select a garment first.")
        
        assets = self.garment.get("assets", [])
        asset = next((a for a in assets if a["name"] == asset_name), None)
        if not asset:
            available = ", ".join(self.list_assets())
            raise ValueError(f"Unknown asset '{asset_name}'. Available: {available}")
        
        allowed_views = asset.get("render_views")
        if allowed_views and self.render_view_code not in allowed_views:
            raise ValueError(
                f"Asset '{asset_name}' is not configured for view '{self.render_view_code}'"
            )
        
        self.asset = asset
        time.sleep(0.2)  # Simulate asset configuration
        print(f"[DEMO] Set asset: {asset_name}")
    
    def render(self) -> str:
        """Mock render implementation"""
        if not self.is_ready_to_render():
            missing = []
            if not self.mode: missing.append("mode")
            if not self.garment: missing.append("garment")
            if not self.fabric: missing.append("fabric")
            if not self.asset: missing.append("asset")
            if not self._garment_loaded: missing.append("garment blend file")
            if not self._fabric_applied: missing.append("fabric material")
            
            raise RuntimeError(f"Missing components: {', '.join(missing)}")
        
        # Generate mock output path
        garment_name = self._active_view_prefix() or "garment"
        fabric_name = self.fabric.get("suffix", self.fabric["name"].lower().replace(" ", "_"))
        asset_suffix = self.asset.get("suffix", self.asset["name"].lower().replace(" ", "_"))
        
        filename = f"{garment_name}-{fabric_name}-{asset_suffix}.png"
        outpath = str((RENDERS_DIR / garment_name / filename))
        
        print(f"[DEMO] Starting render: {filename}")
        
        # Simulate render progress
        for i in range(5):
            print(f"[DEMO] Rendering... {(i+1)*20}%")
            time.sleep(0.5)
        
        print(f"[DEMO] Render completed: {outpath}")
        return outpath


# Alias for compatibility
RenderSession = MockRenderSession