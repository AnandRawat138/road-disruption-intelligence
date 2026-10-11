import React, { useEffect, useState, useMemo } from 'react'
import MapGL, { Source, Layer, NavigationControl, Popup } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'

class ErrorBoundary extends React.Component<any, {hasError: boolean, error: any}> {
  constructor(props: any) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error: any) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) {
      return <div style={{padding: '2rem', color: 'red'}}><h1>Frontend Error</h1><pre>{String(this.state.error?.stack || this.state.error)}</pre></div>;
    }
    return this.props.children;
  }
}

function Dashboard() {
  const [disruptions, setDisruptions] = useState<any[]>([])
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [cursor, setCursor] = useState('auto')
  
  // New features
  const [hoverInfo, setHoverInfo] = useState<any>(null)
  const [routeData, setRouteData] = useState<any>(null)
  const [isRouting, setIsRouting] = useState(false)
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')

  // Fetch the unified disruptions API which now contains all research metrics
  useEffect(() => {
    fetch('/api/disruptions/active')
      .then(res => res.json())
      .then(data => {
          if (Array.isArray(data)) setDisruptions(data);
          else console.error("API did not return an array", data);
      })
      .catch(e => console.error(e))
  }, [])

  const calculateRoute = async () => {
    if (!origin || !destination) return;
    setIsRouting(true);
    try {
      const res = await fetch('/api/routes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ origin, destination })
      });
      const data = await res.json();
      setRouteData(data);
    } catch (e) {
      console.error(e);
    }
    setIsRouting(false);
  }

  // Deduplicate events for the sidebar
  const uniqueEvents = useMemo(() => {
    const eventMap = new globalThis.Map();
    disruptions.forEach((d: any) => {
      if (!eventMap.has(d.event_id)) {
        eventMap.set(d.event_id, {
          ...d,
          affected_roads: []
        });
      }
      eventMap.get(d.event_id).affected_roads.push({
        name: d.road_name,
        type: d.highway_type,
        match: d.matching_confidence
      });
    });
    return Array.from(eventMap.values());
  }, [disruptions]);

  // Color logic for map based on Road Risk Score and Confidence
  const getColor = (risk: number, status: string) => {
    if (status === 'UNRESOLVED' || status === 'UNCERTAIN') return '#95a5a6'; // Grey
    if (risk > 0.7) return '#e74c3c'; // Red - High Risk
    if (risk > 0.4) return '#e67e22'; // Orange - Probable
    return '#f1c40f'; // Yellow - Potential
  };

  const geojson = useMemo(() => ({
    type: 'FeatureCollection',
    features: disruptions.map((d: any) => ({
      type: 'Feature',
      geometry: d.geometry,
      properties: {
        id: d.id,
        event_id: d.event_id,
        event_name: d.event_name,
        color: getColor(d.road_risk_score, d.status),
        selected: d.event_id === selectedEventId
      }
    }))
  }), [disruptions, selectedEventId]);

  const onMapClick = (e: any) => {
    const feature = e.features && e.features[0];
    if (feature) {
      setSelectedEventId(feature.properties.event_id);
    } else {
      setSelectedEventId(null);
    }
  };

  const displayEvents = selectedEventId ? uniqueEvents.filter(e => e.event_id === selectedEventId) : uniqueEvents;

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      {/* Sidebar */}
        <div style={{ width: '500px', background: '#f8fafc', overflowY: 'auto', padding: '1.5rem', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ margin: 0, fontSize: '1.2rem', color: '#0f172a' }}>{selectedEventId ? 'Intelligence Brief' : 'Live Disruptions'}</h2>
            {selectedEventId && (
              <button 
                onClick={() => setSelectedEventId(null)}
                style={{ padding: '0.4rem 0.8rem', background: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}>
                &larr; Overview
              </button>
            )}
          </div>
          
          <div style={{ background: '#fff', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1rem', color: '#1e293b' }}>Time-Aware Routing</h3>
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <input placeholder="Origin" value={origin} onChange={e => setOrigin(e.target.value)} style={{ flex: 1, padding: '0.5rem', border: '1px solid #cbd5e1', borderRadius: '4px' }} />
              <input placeholder="Destination" value={destination} onChange={e => setDestination(e.target.value)} style={{ flex: 1, padding: '0.5rem', border: '1px solid #cbd5e1', borderRadius: '4px' }} />
            </div>
            <button onClick={calculateRoute} disabled={isRouting} style={{ width: '100%', padding: '0.5rem', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}>
              {isRouting ? 'Calculating...' : 'Find Route'}
            </button>
            {routeData?.affected_roads_avoided && (
               <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#10b981', fontWeight: 600 }}>
                 ✓ Alternate route generated to avoid disruptions.
               </div>
            )}
          </div>

          {uniqueEvents.length === 0 ? <p style={{ color: '#64748b' }}>Awaiting pipeline extraction...</p> : null}
          
          {displayEvents.map((e: any) => (
            <div 
              key={e.event_id} 
              onClick={() => !selectedEventId && setSelectedEventId(e.event_id)}
              style={{ 
                background: 'white', 
                padding: '1.2rem', 
                borderRadius: '8px', 
                boxShadow: selectedEventId ? '0 10px 25px -5px rgba(0,0,0,0.1)' : '0 1px 3px rgba(0,0,0,0.1)',
                borderLeft: `5px solid ${getColor(e.road_risk_score, e.status)}`,
                cursor: selectedEventId ? 'default' : 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <h3 style={{ margin: '0 0 0.5rem 0', color: '#1e293b', fontSize: '1.1rem' }}>{e.event_name || e.event_type}</h3>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, padding: '0.2rem 0.5rem', background: '#f1f5f9', color: '#475569', borderRadius: '4px' }}>
                  {e.status}
                </span>
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.8rem', fontSize: '0.85rem', marginBottom: '1rem', color: '#475569' }}>
                <div><strong style={{color:'#1e293b'}}>Impact:</strong> {e.impact_type}</div>
                <div><strong style={{color:'#1e293b'}}>Loc:</strong> {e.city}, {e.state}</div>
                <div><strong style={{color:'#1e293b'}}>AI Risk:</strong> <span style={{ color: getColor(e.road_risk_score, e.status), fontWeight: 700 }}>{(e.road_risk_score * 100).toFixed(0)}%</span></div>
                <div><strong style={{color:'#1e293b'}}>Confidence:</strong> {(e.confidence * 100).toFixed(0)}%</div>
              </div>

              {selectedEventId && (
                <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1rem', fontSize: '0.9rem', color: '#334155' }}>
                  <p><strong>Context:</strong> {e.description}</p>
                  
                  <div style={{ background: '#f8fafc', padding: '1rem', borderRadius: '6px', marginTop: '1rem', border: '1px solid #e2e8f0' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', color: '#0f172a', fontSize: '0.9rem' }}>Temporal Lifeline</h4>
                    <p style={{ margin: '0 0 0.4rem 0', fontSize: '0.85rem', color: '#475569' }}>
                      <em>Raw Extracted:</em> "{e.temporal_expression || 'N/A'}"
                    </p>
                    <div style={{ display: 'flex', gap: '1rem', fontSize: '0.85rem' }}>
                      <div><strong>Start:</strong><br/>{e.start_time ? new Date(e.start_time).toLocaleString() : 'Now'}</div>
                      <div><strong>End:</strong><br/>{e.end_time ? new Date(e.end_time).toLocaleString() : 'Open-Ended'}</div>
                    </div>
                  </div>

                  <div style={{ marginTop: '1rem' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', color: '#0f172a', fontSize: '0.9rem' }}>Affected Routes (Spatial Match)</h4>
                    <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.85rem' }}>
                      {e.affected_roads.map((r: any, idx: number) => (
                        <li key={idx}>
                          <strong>{r.name}</strong> {r.type && `(${r.type})`} 
                          <span style={{ marginLeft: '0.5rem', fontSize: '0.75rem', color: r.match > 0.8 ? '#10b981' : '#f59e0b' }}>
                            [{r.match > 0.8 ? 'DIRECT MATCH' : 'PROXIMITY MATCH'}]
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Map */}
        <div style={{ flex: 1, position: 'relative' }}>
          <MapGL
            initialViewState={{
              longitude: 78.9629,
              latitude: 22.5937,
              zoom: 4.5
            }}
            mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
            interactiveLayerIds={['disruption-lines']}
            onClick={onMapClick}
            onMouseMove={(e: any) => {
              const feature = e.features && e.features[0];
              if (feature) {
                setHoverInfo({
                  longitude: e.lngLat.lng,
                  latitude: e.lngLat.lat,
                  name: feature.properties.event_name,
                  risk: feature.properties.color
                });
                setCursor('pointer');
              } else {
                setHoverInfo(null);
                setCursor('auto');
              }
            }}
            onMouseLeave={() => { setHoverInfo(null); setCursor('auto'); }}
            cursor={cursor}
          >
            <NavigationControl position="bottom-right" />
            
            {/* Draw Routes if available */}
            {routeData?.normal_geometry && (
              <Source id="normal-route" type="geojson" data={routeData.normal_geometry as any}>
                <Layer id="normal-route-line" type="line" paint={{'line-color': '#94a3b8', 'line-width': 4, 'line-dasharray': [2, 2]}} />
              </Source>
            )}
            {routeData?.disruption_aware_geometry && (
              <Source id="aware-route" type="geojson" data={routeData.disruption_aware_geometry as any}>
                <Layer id="aware-route-line" type="line" paint={{'line-color': '#3b82f6', 'line-width': 5}} />
              </Source>
            )}

            <Source id="disruptions" type="geojson" data={geojson as any}>
              <Layer
                id="disruption-lines"
                type="line"
                paint={{
                  'line-color': ['get', 'color'],
                  'line-width': ['case', ['boolean', ['get', 'selected'], false], 10, 5],
                  'line-opacity': ['case', ['boolean', ['get', 'selected'], false], 1, 0.8]
                }}
              />
            </Source>

            {hoverInfo && (
              <Popup
                longitude={hoverInfo.longitude}
                latitude={hoverInfo.latitude}
                closeButton={false}
                closeOnClick={false}
                anchor="top"
                style={{ fontFamily: 'Inter, sans-serif' }}
              >
                <div style={{ padding: '0.2rem', color: '#0f172a' }}>
                  <strong style={{ borderLeft: `4px solid ${hoverInfo.risk}`, paddingLeft: '8px' }}>
                    {hoverInfo.name}
                  </strong>
                </div>
              </Popup>
            )}
          </MapGL>
        </div>
      </div>
  )
}

function AdminSettings() {
  const [configs, setConfigs] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api/admin/')
      .then(res => res.json())
      .then(data => setConfigs(data));
  }, []);

  const handleUpdate = async (key: string, newValue: string) => {
    setConfigs(configs.map(c => c.key === key ? { ...c, value: newValue } : c));
    await fetch(`/api/admin/${key}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: newValue })
    });
  };

  return (
    <div style={{ padding: '2rem', background: '#f8fafc', flex: 1, overflowY: 'auto' }}>
      <div style={{ maxWidth: '800px', margin: '0 auto', background: 'white', borderRadius: '8px', padding: '2rem', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
        <h2 style={{ borderBottom: '2px solid #e2e8f0', paddingBottom: '0.5rem', marginBottom: '1.5rem', color: '#0f172a' }}>Enterprise Settings Control Center</h2>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {configs.map(config => (
            <div key={config.key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: '#f1f5f9', borderRadius: '6px' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, color: '#1e293b' }}>{config.key}</div>
                <div style={{ fontSize: '0.85rem', color: '#64748b' }}>{config.description}</div>
              </div>
              <div style={{ width: '200px' }}>
                {config.type === 'boolean' ? (
                  <select 
                    value={config.value} 
                    onChange={e => handleUpdate(config.key, e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                  >
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </select>
                ) : (
                  <input 
                    type={config.is_sensitive ? 'password' : 'text'}
                    value={config.value}
                    onChange={e => handleUpdate(config.key, e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function MainApp() {
  const [activeView, setActiveView] = useState<'dashboard' | 'settings'>('dashboard');

  return (
    <div style={{ display: 'flex', height: '100vh', flexDirection: 'column', fontFamily: 'Inter, sans-serif' }}>
      <header style={{ background: '#1e293b', color: 'white', padding: '1rem 1.5rem', display: 'flex', alignItems: 'center' }}>
        <h1 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 600, flex: 1 }}>GeoSpatial Transport Intelligence</h1>
        
        <div style={{ display: 'flex', gap: '1.5rem', marginRight: '2rem' }}>
          <button 
            onClick={() => setActiveView('dashboard')}
            style={{ background: 'transparent', border: 'none', color: activeView === 'dashboard' ? '#60a5fa' : 'white', fontWeight: 600, cursor: 'pointer', fontSize: '1rem' }}
          >Live Map</button>
          <button 
            onClick={() => setActiveView('settings')}
            style={{ background: 'transparent', border: 'none', color: activeView === 'settings' ? '#60a5fa' : 'white', fontWeight: 600, cursor: 'pointer', fontSize: '1rem' }}
          >Settings</button>
        </div>

        {activeView === 'dashboard' && (
          <div style={{ display: 'flex', gap: '1rem', fontSize: '0.9rem' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><div style={{width: 12, height: 12, background: '#e74c3c', borderRadius: '50%'}}></div> High Risk</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><div style={{width: 12, height: 12, background: '#e67e22', borderRadius: '50%'}}></div> Probable</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><div style={{width: 12, height: 12, background: '#f1c40f', borderRadius: '50%'}}></div> Potential</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><div style={{width: 12, height: 12, background: '#95a5a6', borderRadius: '50%'}}></div> Uncertain</span>
          </div>
        )}
      </header>

      {activeView === 'dashboard' ? <Dashboard /> : <AdminSettings />}
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <MainApp />
    </ErrorBoundary>
  );
}
