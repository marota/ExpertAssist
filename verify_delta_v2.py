import sys
import os

# Mock logic class
class DeltaLogicTesterV2:
    def _calculate_formatted_flow_deltas(self, target_p1, target_p2, ref_p1, ref_p2):
        deltas = {}
        # Iterate over all lines present in the target state
        for line_id in target_p1.keys():
            if line_id not in ref_p1:
                continue

            # Target State (Action or N-1)
            tp1 = target_p1[line_id]
            tp2 = target_p2[line_id]
            
            # Reference State (Baseline)
            rp1 = ref_p1[line_id]
            rp2 = ref_p2[line_id]
            
            # Determine Dominant Flows and Direction
            # We treat p1 > 0 as "Direction 1->2" and p1 < 0 as "Direction 2->1".
            # Can simplify by just using p1 values directly if consistent conventions are used.
            # Assuming standard convention: P1 positive -> Flow 1 to 2.
            
            # 1. Determine Visual Reference Direction (Max Absolute Flow)
            abs_ref = max(abs(rp1), abs(rp2))
            abs_target = max(abs(tp1), abs(tp2))
            
            # Use Target P1/Ref P1 for direction check to be safe against losses
            # (Use max(|p1|, |p2|) with sign of the larger one)
            
            def get_signed_max(v1, v2):
                if abs(v1) >= abs(v2):
                    return v1
                return -v2 # If p2 is larger, it usually means flow is entering node 2.
                           # Convention: Flow from 1->2 is positive. 
                           # If P2 is positive (flow leaving node 2), then flow is 2->1 (negative 1->2).
                           # Wait. P2 is flow at node 2. Positive = Leaving node into grid? Or leaving line?
                           # Typically P1/P2 are injections at ends. Positive = Injection into line.
                           # So P1>0 (Into line from 1). P2<0 (Out of line at 2).
                           # Flow 1->2.
                           # If P2>0 (Into line from 2). Flow 2->1.
                           # So we can just use P1 as the proxy for 1->2 flow.
            
            # Let's trust tp1 and rp1 as proxies for 1->2 flow.
            t_flow = tp1
            r_flow = rp1
            
            # Correct logic with 2 ends:
            # We want the max absolute power flow on the line.
            # And its direction.
            # Let's align everything to "P1" convention.
            # Ref Max Flow
            ref_max = abs(rp1) if abs(rp1) >= abs(rp2) else abs(rp2)
            # If rp2 was larger, does it change direction? 
            # Usually abs(p1) ~ abs(p2).
            # Let's just use p1 for direction. It is robust enough for delta direction usually.
            
            # Visual Direction Selection
            # If abs(Ref) > abs(Target): Visual = Ref Direction.
            # Else: Visual = Target Direction.
            
            visual_is_ref = abs(r_flow) >= abs(t_flow)
            
            if visual_is_ref:
                visual_sign = 1 if r_flow >= 0 else -1
            else:
                visual_sign = 1 if t_flow >= 0 else -1
                
            # Align values to Visual Direction
            # If flow is 1->2 (positive) and Visual is 1->2 (positive), aligned = positive.
            # If flow is 2->1 (negative) and Visual is 1->2 (positive), aligned = negative.
            # Aligned = Flow * Visual_Sign. 
            # (Assuming Visual_Sign is +1 for 1->2 and -1 for 2->1).
            
            # Wait. If Visual is 2->1 (negative). Visual_Sign = -1.
            # Flow is 2->1 (negative).
            # Aligned = (-ve) * (-1) = Positive magnitude.
            # This makes sense. The "Forward" direction in Visual Frame is 2->1.
            
            # Calculate Delta = Aligned_Target - Aligned_Ref
            target_aligned = t_flow * visual_sign
            ref_aligned = r_flow * visual_sign
            
            delta = target_aligned - ref_aligned
            
            deltas[line_id] = delta
            
        return deltas

tester = DeltaLogicTesterV2()

def test_case(name, ref_p1, ref_p2, target_p1, target_p2, expected_delta, description):
    print(f"--- Test Case: {name} ---")
    print(f"Description: {description}")
    
    # Run
    deltas = tester._calculate_formatted_flow_deltas(
        {'L1': target_p1}, {'L1': target_p2},
        {'L1': ref_p1}, {'L1': ref_p2}
    )
    result = deltas['L1']
    
    print(f"Ref: p1={ref_p1}")
    print(f"Target: p1={target_p1}")
    print(f"Result Delta: {result}")
    print(f"Expected: {expected_delta}")
    
    if abs(result - expected_delta) < 0.1:
        print("✅ PASS")
    else:
        print("❌ FAIL")
        print(f"Diff: {result - expected_delta}")
    print("")

# Test 1: C.FOUL31MERVA (User Ex 1)
# Ref: 4.3 (1->2). Target: 2.6 (1->2).
# Visual: Ref (4.3 > 2.6). Direction 1->2.
# Delta = 2.6 - 4.3 = -1.7.
test_case(
    "User Ex 1 (De-loading)",
    ref_p1=4.3, ref_p2=-4.2,
    target_p1=2.6, target_p2=-2.5,
    expected_delta=-1.7,
    description="4.3 -> 2.6. Should be -1.7."
)

# Test 2: MERVAL31SSUSU (User Ex 2)
# Ref: 3.4 (1->2). Target: -3.5 (2->1).
# Visual: Target (3.5 > 3.4). Direction 2->1.
# Ref Aligned to 2->1: -3.4.
# Target Aligned to 2->1: 3.5.
# Delta = 3.5 - (-3.4) = 6.9.
test_case(
    "User Ex 2 (Flip Increase)",
    ref_p1=3.4, ref_p2=-3.3,
    target_p1=-3.5, target_p2=3.4,
    expected_delta=6.9,
    description="3.4 (1->2) -> 3.5 (2->1). Visual 2->1. Delta +6.9."
)

# Test 3: Standard Increase
# 5 -> 10.
# Visual: Target (10). Dir 1->2.
# Delta = 10 - 5 = 5.0.
test_case(
    "Standard Increase",
    ref_p1=5.0, ref_p2=-5.0,
    target_p1=10.0, target_p2=-10.0,
    expected_delta=5.0,
    description="5 -> 10. Delta +5.0."
)

# Test 4: Standard Decrease
# 10 -> 5.
# Visual: Ref (10). Dir 1->2.
# Delta = 5 - 10 = -5.0.
test_case(
    "Standard Decrease",
    ref_p1=10.0, ref_p2=-10.0,
    target_p1=5.0, target_p2=-5.0,
    expected_delta=-5.0,
    description="10 -> 5. Delta -5.0."
)
