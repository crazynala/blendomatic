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
            "garment_prefix": self.garment.get("output_prefix", "mock") if self.garment else None,
            "fabric_name": self.fabric["name"] if self.fabric else None,
            "asset_name": self.asset["name"] if self.asset else None,
            "garment_loaded": self._garment_loaded,
            "fabric_applied": self._fabric_applied,
            "ready_to_render": self.is_ready_to_render()
        }
    
    def is_ready_to_render(self) -> bool:
        return all([
            self.mode,
            self.garment,
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
        
        print(f"[DEMO] Loading garment blend file... (simulated)")
        time.sleep(1)  # Simulate blend file loading
        
        # Reset dependent state
        self.asset = None
        self._garment_loaded = True
        self._fabric_applied = False
        
        print(f"[DEMO] Set garment: {self.garment.get('name', garment_name)}")
    
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
        garment_name = self.garment.get("output_prefix", "garment")
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