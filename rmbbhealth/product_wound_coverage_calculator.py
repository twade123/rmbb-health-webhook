#!/usr/bin/env python3
"""
Product Wound Coverage Calculator

Converts JavaScript wound coverage calculation algorithm to Python.
Calculates optimal product size combinations with 15% CMS waste factor.
Maps results to GHL custom field IDs for webhook updates.

Based on: rmbbhealth cell prodcts formula.txt
"""
import json
import math
from typing import Dict, List, Tuple, Optional

class ProductWoundCoverageCalculator:
    """
    Calculates optimal product size combinations for wound coverage
    with 15% CMS waste allowance factor.
    """
    
    def __init__(self):
        """Initialize with product sizes and GHL custom field mappings."""
        
        # Load all custom field IDs created for size-specific products
        self.size_field_mapping = self._load_size_field_mapping()
        
        # Product sizes from formula file (in cm²)
        self.product_sizes = {
            'AmnioAmp-MP': {
                'q_code': 'Q4250',
                'available_sizes': {
                    '2x2': 4, '2x3': 6, '2x4': 8, 
                    '4x4': 16, '4x6': 24, '4x8': 32
                }
            },
            'Palingen': {
                'q_code': 'Q4173', 
                'available_sizes': {
                    '1x1': 1, '2x3': 6, '4x4': 16, 
                    '4x6': 24, '4x8': 32
                }
            },
            'Simplimax': {
                'q_code': 'Q4341',
                'available_sizes': {
                    '2x2': 4, '2x3': 6, '4x4': 16,
                    '4x6': 24, '4x8': 32
                }
            },
            'Xcell Amnio Matrix': {
                'q_code': 'Q4280',
                'available_sizes': {
                    '2x2': 4, '2x4': 8, '4x4': 16, '4x7': 28
                }
            },
            'AmnioMaxx': {
                'q_code': 'Q4239',
                'available_sizes': {
                    '2x2': 4, '2x3': 6, '2x4': 8, 
                    '4x4': 16, '4x6': 24, '4x8': 32, '3x3': 9
                }
            },
            'Dermabind-FM': {
                'q_code': 'Unknown',
                'available_sizes': {
                    '2x2': 4, '3x3': 9, '4x4': 16, '6.5x6.5': 42.25
                }
            },
            'Derm Maxx': {
                'q_code': 'Q4238',
                'available_sizes': {
                    '1x1': 1, '2x2': 4, '2x4': 8,
                    '4x4': 16, '4x8': 32, '5x10': 50
                }
            },
            'Esano ACA': {
                'q_code': 'Q4275',
                'available_sizes': {
                    '2x2': 4, '2x3': 6, '4x4': 16,
                    '4x6': 24, '4x8': 32
                }
            
            },
            'Membrane Wrap Q2': {
                'q_code': 'Q4205',
                'available_sizes': {
                    '1x1': 1, '2x2': 4, '2x3': 6,
                    '4x4': 16, '4x6': 24, '4x8': 32
                }
            },
            'Membrane Wrap H': {
                'q_code': 'Q4290',
                'available_sizes': {
                    '2x2': 4, '2x3': 6, '4x4': 16,
                    '4x6': 24, '4x8': 32
                }
            }
        }
    
    def _load_size_field_mapping(self) -> Dict[str, str]:
        """Load custom field IDs for all product sizes."""
        try:
            with open('/Users/timothywade/Jarvis/product_size_custom_fields_exact.json', 'r') as f:
                data = json.load(f)
            
            # Create mapping: "Product Size" -> "field_id"
            mapping = {}
            for field in data.get('created_fields', []):
                product = field['product']
                size = field['size']
                field_id = field['field_id']
                key = f"{product} {size}"
                mapping[key] = field_id
            
            print(f"✅ Loaded {len(mapping)} product size field mappings")
            return mapping
            
        except FileNotFoundError:
            print("❌ Custom field mapping file not found")
            return {}
        except Exception as e:
            print(f"❌ Error loading field mapping: {e}")
            return {}
    
    def calculate_wound_coverage(self, product_name: str, wound_size_cm2: float, 
                                pre_selected_product: str = None) -> Dict:
        """
        Calculate optimal product size combination for wound coverage.
        
        Args:
            product_name: Name of the approved product
            wound_size_cm2: Total wound size in cm²
            pre_selected_product: Optional preferred product size
            
        Returns:
            Dict with calculation results and GHL field mappings
        """
        
        # Input validation
        if not isinstance(wound_size_cm2, (int, float)) or wound_size_cm2 <= 0:
            return {
                "success": False,
                "error": "Invalid wound size - must be positive number",
                "wound_size": wound_size_cm2
            }
        
        if product_name not in self.product_sizes:
            return {
                "success": False,
                "error": f"Product not found: {product_name}",
                "available_products": list(self.product_sizes.keys())
            }
        
        # Get product information
        product_info = self.product_sizes[product_name]
        available_sizes = product_info['available_sizes']
        q_code = product_info['q_code']
        
        # CMS waste allowance: 15% additional coverage
        waste_factor = 1.15
        effective_wound_size = math.ceil(wound_size_cm2 * waste_factor)
        
        print(f"🧮 WOUND COVERAGE CALCULATION")
        print(f"   Product: {product_name} ({q_code})")
        print(f"   Original wound size: {wound_size_cm2} cm²")
        print(f"   With 15% waste factor: {effective_wound_size} cm²")
        
        # Calculate optimal size combination using greedy algorithm
        size_combination = self._calculate_optimal_sizes(
            available_sizes, 
            effective_wound_size, 
            pre_selected_product
        )
        
        if not size_combination:
            return {
                "success": False,
                "error": "Could not calculate optimal size combination",
                "wound_size": wound_size_cm2,
                "effective_size": effective_wound_size
            }
        
        # Calculate total coverage and waste
        total_cm2 = sum(size_info['cm2'] * size_info['units'] 
                       for size_info in size_combination.values())
        actual_waste_percent = ((total_cm2 / wound_size_cm2) - 1) * 100
        
        # Map to GHL custom fields
        ghl_field_updates = self._map_to_ghl_fields(product_name, size_combination)
        
        result = {
            "success": True,
            "product_name": product_name,
            "q_code": q_code,
            "wound_size_cm2": wound_size_cm2,
            "effective_wound_size_cm2": effective_wound_size,
            "waste_factor": waste_factor,
            "size_combination": size_combination,
            "total_coverage_cm2": total_cm2,
            "actual_waste_percent": round(actual_waste_percent, 2),
            "ghl_field_updates": ghl_field_updates,
            "calculation_summary": self._generate_summary(size_combination, total_cm2, actual_waste_percent)
        }
        
        print(f"   ✅ Calculation complete: {len(size_combination)} different sizes")
        print(f"   📊 Total coverage: {total_cm2} cm² ({actual_waste_percent:.1f}% waste)")
        
        return result
    
    def _calculate_optimal_sizes(self, available_sizes: Dict[str, float], 
                               effective_wound_size: float, 
                               pre_selected_size: str = None) -> Dict:
        """
        Calculate optimal size combination using greedy algorithm.
        Prioritizes pre-selected size if provided.
        """
        
        # Sort sizes by area (largest first) for greedy algorithm
        sorted_sizes = sorted(available_sizes.items(), 
                            key=lambda x: x[1], reverse=True)
        
        units = {}
        remaining = effective_wound_size
        
        # Prioritize pre-selected size if provided
        if pre_selected_size and pre_selected_size in available_sizes:
            pre_size_cm2 = available_sizes[pre_selected_size]
            count = math.floor(remaining / pre_size_cm2)
            if count > 0:
                units[pre_selected_size] = {
                    'units': count,
                    'cm2': pre_size_cm2,
                    'total_cm2': count * pre_size_cm2
                }
                remaining = remaining % pre_size_cm2
                print(f"   🎯 Pre-selected {pre_selected_size}: {count} units ({count * pre_size_cm2} cm²)")
        
        # Use greedy algorithm for remaining coverage
        for size_name, size_cm2 in sorted_sizes:
            if remaining > 0 and size_name != pre_selected_size:
                count = math.floor(remaining / size_cm2)
                if count > 0:
                    units[size_name] = {
                        'units': count,
                        'cm2': size_cm2,
                        'total_cm2': count * size_cm2
                    }
                    remaining = remaining % size_cm2
                    print(f"   📐 {size_name}: {count} units ({count * size_cm2} cm²)")
        
        # If there's still remaining area, use smallest available size
        if remaining > 0:
            smallest_size = min(available_sizes.items(), key=lambda x: x[1])
            smallest_name, smallest_cm2 = smallest_size
            
            additional_units = math.ceil(remaining / smallest_cm2)
            
            if smallest_name in units:
                units[smallest_name]['units'] += additional_units
                units[smallest_name]['total_cm2'] += additional_units * smallest_cm2
            else:
                units[smallest_name] = {
                    'units': additional_units,
                    'cm2': smallest_cm2,
                    'total_cm2': additional_units * smallest_cm2
                }
            
            print(f"   ➕ Additional {smallest_name}: {additional_units} units for remaining {remaining:.1f} cm²")
        
        return units
    
    def _map_to_ghl_fields(self, product_name: str, size_combination: Dict) -> List[Dict]:
        """Map calculated sizes to GHL custom field updates."""
        
        field_updates = []
        
        for size_name, size_info in size_combination.items():
            field_key = f"{product_name} {size_name}"
            field_id = self.size_field_mapping.get(field_key)
            
            if field_id:
                field_updates.append({
                    "id": field_id,
                    "value": str(size_info['units']),
                    "product": product_name,
                    "size": size_name,
                    "units": size_info['units'],
                    "cm2_per_unit": size_info['cm2'],
                    "total_cm2": size_info['total_cm2']
                })
                print(f"   🔗 Mapped {field_key}: {size_info['units']} units → Field ID {field_id}")
            else:
                print(f"   ⚠️ No field mapping found for: {field_key}")
        
        return field_updates
    
    def _generate_summary(self, size_combination: Dict, total_cm2: float, 
                         actual_waste: float) -> str:
        """Generate human-readable calculation summary."""
        
        parts = []
        for size_name, size_info in size_combination.items():
            units = size_info['units']
            parts.append(f"{units}x {size_name}")
        
        summary = f"{', '.join(parts)} (Total: {total_cm2} cm², Waste: {actual_waste:.1f}%)"
        return summary
    
    def process_rmbb_approval(self, case_data: Dict) -> Dict:
        """
        Process RMBB Health approval data to extract product and wound size,
        then calculate optimal product combination.
        
        Args:
            case_data: RMBB Health case data from webhook
            
        Returns:
            Dict with calculation results and GHL field updates
        """
        
        # Extract product information from case data
        # This will need to be customized based on actual RMBB Health data structure
        
        product_name = None
        wound_size_cm2 = None
        
        # TODO: Extract actual product name and wound size from RMBB case data
        # This depends on the structure of the RMBB Health approval JSON
        
        # For now, return structure for integration
        return {
            "success": False,
            "error": "RMBB approval processing not yet implemented",
            "todo": "Extract product_name and wound_size_cm2 from case_data",
            "case_data_keys": list(case_data.keys()) if case_data else []
        }


def test_calculator():
    """Test the wound coverage calculator with sample data."""
    
    calculator = ProductWoundCoverageCalculator()
    
    # Test case 1: AmnioMaxx with 20 cm² wound
    print("=" * 60)
    print("TEST CASE 1: AmnioMaxx 20 cm² wound")
    print("=" * 60)
    
    result1 = calculator.calculate_wound_coverage(
        product_name="AmnioMaxx",
        wound_size_cm2=20.0,
        pre_selected_product="4x4"
    )
    
    if result1["success"]:
        print(f"✅ Success: {result1['calculation_summary']}")
        print(f"📋 GHL Field Updates: {len(result1['ghl_field_updates'])} fields")
    else:
        print(f"❌ Failed: {result1['error']}")
    
    # Test case 2: Palingen with 12 cm² wound
    print("\n" + "=" * 60)
    print("TEST CASE 2: Palingen 12 cm² wound")
    print("=" * 60)
    
    result2 = calculator.calculate_wound_coverage(
        product_name="Palingen", 
        wound_size_cm2=12.0
    )
    
    if result2["success"]:
        print(f"✅ Success: {result2['calculation_summary']}")
        print(f"📋 GHL Field Updates: {len(result2['ghl_field_updates'])} fields")
    else:
        print(f"❌ Failed: {result2['error']}")
    
    return result1, result2


if __name__ == "__main__":
    # Run test cases
    test_calculator()