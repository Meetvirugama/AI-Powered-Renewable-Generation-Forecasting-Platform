from typing import Optional, Dict, Any

class MockRAGCopilot:
    """Mock RAG Copilot returning structured explanations."""
    
    def query(self, question: str, plant_id: Optional[str] = None, block_no: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        q_lower = question.lower()
        
        if 'penalty' in q_lower or 'penalised' in q_lower:
            answer = "Based on CERC DSM Regulations 2026, penalties are computed based on deviations from the scheduled generation. When the deviation exceeds the tolerance band, a penalty is applied proportional to the Normal Charge for Deviation (NCD)."
            citations = [
                {'clause': 'Regulation 7.2', 'page': 12, 'doc': 'CERC_DSM_Amendment_2026.pdf', 'url': ''}
            ]
        elif 'tolerance' in q_lower:
            answer = "The tolerance band for wind and solar generators defines the permissible deviation limit without incurring penalties. It is calculated based on the Available Capacity (AvC) and scheduled generation, with varying bands for solar (typically 10%) and wind (typically 15%)."
            citations = [
                {'clause': 'Regulation 5.1', 'page': 8, 'doc': 'CERC_DSM_Regulations_2024.pdf', 'url': ''}
            ]
        elif 'pooling' in q_lower:
            answer = "Portfolio pooling allows multiple renewable generators to aggregate their schedules and actuals. This mechanism offsets over-injections from one plant with under-injections from another, reducing the net deviation and lowering the overall DSM penalty for the portfolio."
            citations = [
                {'clause': 'Regulation 10.3', 'page': 18, 'doc': 'CERC_DSM_Amendment_2026.pdf', 'url': ''}
            ]
        else:
            answer = "According to CERC DSM Regulations, proper scheduling and forecasting are mandatory for all grid-connected renewable generators to ensure grid stability and minimize commercial impacts."
            citations = [
                {'clause': 'General Guidelines', 'page': 1, 'doc': 'CERC_DSM_Regulations_2024.pdf', 'url': ''}
            ]
            
        return {
            'answer': answer,
            'citations': citations,
            'engine_values': context or {'penalty_inr': 0.0, 'deviation_pct': 0.0}
        }
