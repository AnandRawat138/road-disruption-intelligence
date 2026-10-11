import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import React, { useEffect, useState, useMemo } from 'react';
import Map, { Source, Layer, NavigationControl, Popup } from 'react-map-gl';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
class ErrorBoundary extends React.Component {
    constructor(props) { super(props); this.state = { hasError: false, error: null }; }
    static getDerivedStateFromError(error) { return { hasError: true, error }; }
    render() {
        if (this.state.hasError) {
            return _jsxs("div", { style: { padding: '2rem', color: 'red' }, children: [_jsx("h1", { children: "Frontend Error" }), _jsx("pre", { children: String(this.state.error?.stack || this.state.error) })] });
        }
        return this.props.children;
    }
}
function Dashboard() {
    const [disruptions, setDisruptions] = useState([]);
    const [selectedEventId, setSelectedEventId] = useState(null);
    const [cursor, setCursor] = useState('auto');
    // New features
    const [hoverInfo, setHoverInfo] = useState(null);
    const [routeData, setRouteData] = useState(null);
    const [isRouting, setIsRouting] = useState(false);
    const [origin, setOrigin] = useState('');
    const [destination, setDestination] = useState('');
    // Fetch the unified disruptions API which now contains all research metrics
    useEffect(() => {
        fetch('/api/disruptions/active')
            .then(res => res.json())
            .then(data => {
            if (Array.isArray(data))
                setDisruptions(data);
            else
                console.error("API did not return an array", data);
        })
            .catch(e => console.error(e));
    }, []);
    const calculateRoute = async () => {
        if (!origin || !destination)
            return;
        setIsRouting(true);
        try {
            const res = await fetch('/api/routes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ origin, destination })
            });
            const data = await res.json();
            setRouteData(data);
        }
        catch (e) {
            console.error(e);
        }
        setIsRouting(false);
    };
    // Deduplicate events for the sidebar
    const uniqueEvents = useMemo(() => {
        const eventMap = new globalThis.Map();
        disruptions.forEach((d) => {
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
    const getColor = (risk, status) => {
        if (status === 'UNRESOLVED' || status === 'UNCERTAIN')
            return '#95a5a6'; // Grey
        if (risk > 0.7)
            return '#e74c3c'; // Red - High Risk
        if (risk > 0.4)
            return '#e67e22'; // Orange - Probable
        return '#f1c40f'; // Yellow - Potential
    };
    const geojson = useMemo(() => ({
        type: 'FeatureCollection',
        features: disruptions.map((d) => ({
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
    const onMapClick = (e) => {
        const feature = e.features && e.features[0];
        if (feature) {
            setSelectedEventId(feature.properties.event_id);
        }
        else {
            setSelectedEventId(null);
        }
    };
    const displayEvents = selectedEventId ? uniqueEvents.filter(e => e.event_id === selectedEventId) : uniqueEvents;
    return (_jsxs("div", { style: { display: 'flex', flex: 1, overflow: 'hidden' }, children: [_jsxs("div", { style: { width: '500px', background: '#f8fafc', overflowY: 'auto', padding: '1.5rem', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '1rem' }, children: [_jsxs("div", { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' }, children: [_jsx("h2", { style: { margin: 0, fontSize: '1.2rem', color: '#0f172a' }, children: selectedEventId ? 'Intelligence Brief' : 'Live Disruptions' }), selectedEventId && (_jsx("button", { onClick: () => setSelectedEventId(null), style: { padding: '0.4rem 0.8rem', background: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }, children: "\u2190 Overview" }))] }), _jsxs("div", { style: { background: '#fff', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }, children: [_jsx("h3", { style: { margin: '0 0 0.5rem 0', fontSize: '1rem', color: '#1e293b' }, children: "Time-Aware Routing" }), _jsxs("div", { style: { display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }, children: [_jsx("input", { placeholder: "Origin", value: origin, onChange: e => setOrigin(e.target.value), style: { flex: 1, padding: '0.5rem', border: '1px solid #cbd5e1', borderRadius: '4px' } }), _jsx("input", { placeholder: "Destination", value: destination, onChange: e => setDestination(e.target.value), style: { flex: 1, padding: '0.5rem', border: '1px solid #cbd5e1', borderRadius: '4px' } })] }), _jsx("button", { onClick: calculateRoute, disabled: isRouting, style: { width: '100%', padding: '0.5rem', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }, children: isRouting ? 'Calculating...' : 'Find Route' }), routeData?.affected_roads_avoided && (_jsx("div", { style: { marginTop: '0.5rem', fontSize: '0.85rem', color: '#10b981', fontWeight: 600 }, children: "\u2713 Alternate route generated to avoid disruptions." }))] }), uniqueEvents.length === 0 ? _jsx("p", { style: { color: '#64748b' }, children: "Awaiting pipeline extraction..." }) : null, displayEvents.map((e) => (_jsxs("div", { onClick: () => !selectedEventId && setSelectedEventId(e.event_id), style: {
                            background: 'white',
                            padding: '1.2rem',
                            borderRadius: '8px',
                            boxShadow: selectedEventId ? '0 10px 25px -5px rgba(0,0,0,0.1)' : '0 1px 3px rgba(0,0,0,0.1)',
                            borderLeft: `5px solid ${getColor(e.road_risk_score, e.status)}`,
                            cursor: selectedEventId ? 'default' : 'pointer',
                            transition: 'all 0.2s ease'
                        }, children: [_jsxs("div", { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }, children: [_jsx("h3", { style: { margin: '0 0 0.5rem 0', color: '#1e293b', fontSize: '1.1rem' }, children: e.event_name || e.event_type }), _jsx("span", { style: { fontSize: '0.75rem', fontWeight: 700, padding: '0.2rem 0.5rem', background: '#f1f5f9', color: '#475569', borderRadius: '4px' }, children: e.status })] }), _jsxs("div", { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.8rem', fontSize: '0.85rem', marginBottom: '1rem', color: '#475569' }, children: [_jsxs("div", { children: [_jsx("strong", { style: { color: '#1e293b' }, children: "Impact:" }), " ", e.impact_type] }), _jsxs("div", { children: [_jsx("strong", { style: { color: '#1e293b' }, children: "Loc:" }), " ", e.city, ", ", e.state] }), _jsxs("div", { children: [_jsx("strong", { style: { color: '#1e293b' }, children: "AI Risk:" }), " ", _jsxs("span", { style: { color: getColor(e.road_risk_score, e.status), fontWeight: 700 }, children: [(e.road_risk_score * 100).toFixed(0), "%"] })] }), _jsxs("div", { children: [_jsx("strong", { style: { color: '#1e293b' }, children: "Confidence:" }), " ", (e.confidence * 100).toFixed(0), "%"] })] }), selectedEventId && (_jsxs("div", { style: { borderTop: '1px solid #e2e8f0', paddingTop: '1rem', fontSize: '0.9rem', color: '#334155' }, children: [_jsxs("p", { children: [_jsx("strong", { children: "Context:" }), " ", e.description] }), _jsxs("div", { style: { background: '#f8fafc', padding: '1rem', borderRadius: '6px', marginTop: '1rem', border: '1px solid #e2e8f0' }, children: [_jsx("h4", { style: { margin: '0 0 0.5rem 0', color: '#0f172a', fontSize: '0.9rem' }, children: "Temporal Lifeline" }), _jsxs("p", { style: { margin: '0 0 0.4rem 0', fontSize: '0.85rem', color: '#475569' }, children: [_jsx("em", { children: "Raw Extracted:" }), " \"", e.temporal_expression || 'N/A', "\""] }), _jsxs("div", { style: { display: 'flex', gap: '1rem', fontSize: '0.85rem' }, children: [_jsxs("div", { children: [_jsx("strong", { children: "Start:" }), _jsx("br", {}), e.start_time ? new Date(e.start_time).toLocaleString() : 'Now'] }), _jsxs("div", { children: [_jsx("strong", { children: "End:" }), _jsx("br", {}), e.end_time ? new Date(e.end_time).toLocaleString() : 'Open-Ended'] })] })] }), _jsxs("div", { style: { marginTop: '1rem' }, children: [_jsx("h4", { style: { margin: '0 0 0.5rem 0', color: '#0f172a', fontSize: '0.9rem' }, children: "Affected Routes (Spatial Match)" }), _jsx("ul", { style: { margin: 0, paddingLeft: '1.2rem', fontSize: '0.85rem' }, children: e.affected_roads.map((r, idx) => (_jsxs("li", { children: [_jsx("strong", { children: r.name }), " ", r.type && `(${r.type})`, _jsxs("span", { style: { marginLeft: '0.5rem', fontSize: '0.75rem', color: r.match > 0.8 ? '#10b981' : '#f59e0b' }, children: ["[", r.match > 0.8 ? 'DIRECT MATCH' : 'PROXIMITY MATCH', "]"] })] }, idx))) })] })] }))] }, e.event_id)))] }), _jsx("div", { style: { flex: 1, position: 'relative' }, children: _jsxs(Map, { initialViewState: {
                        longitude: 78.9629,
                        latitude: 22.5937,
                        zoom: 4.5
                    }, mapStyle: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json", mapLib: maplibregl, interactiveLayerIds: ['disruption-lines'], onClick: onMapClick, onMouseMove: (e) => {
                        const feature = e.features && e.features[0];
                        if (feature) {
                            setHoverInfo({
                                longitude: e.lngLat.lng,
                                latitude: e.lngLat.lat,
                                name: feature.properties.event_name,
                                risk: feature.properties.color
                            });
                            setCursor('pointer');
                        }
                        else {
                            setHoverInfo(null);
                            setCursor('auto');
                        }
                    }, onMouseLeave: () => { setHoverInfo(null); setCursor('auto'); }, cursor: cursor, children: [_jsx(NavigationControl, { position: "bottom-right" }), routeData?.normal_geometry && (_jsx(Source, { id: "normal-route", type: "geojson", data: routeData.normal_geometry, children: _jsx(Layer, { id: "normal-route-line", type: "line", paint: { 'line-color': '#94a3b8', 'line-width': 4, 'line-dasharray': [2, 2] } }) })), routeData?.disruption_aware_geometry && (_jsx(Source, { id: "aware-route", type: "geojson", data: routeData.disruption_aware_geometry, children: _jsx(Layer, { id: "aware-route-line", type: "line", paint: { 'line-color': '#3b82f6', 'line-width': 5 } }) })), _jsx(Source, { id: "disruptions", type: "geojson", data: geojson, children: _jsx(Layer, { id: "disruption-lines", type: "line", paint: {
                                    'line-color': ['get', 'color'],
                                    'line-width': ['case', ['boolean', ['get', 'selected'], false], 10, 5],
                                    'line-opacity': ['case', ['boolean', ['get', 'selected'], false], 1, 0.8]
                                } }) }), hoverInfo && (_jsx(Popup, { longitude: hoverInfo.longitude, latitude: hoverInfo.latitude, closeButton: false, closeOnClick: false, anchor: "top", style: { fontFamily: 'Inter, sans-serif' }, children: _jsx("div", { style: { padding: '0.2rem', color: '#0f172a' }, children: _jsx("strong", { style: { borderLeft: `4px solid ${hoverInfo.risk}`, paddingLeft: '8px' }, children: hoverInfo.name }) }) }))] }) })] }));
}
function AdminSettings() {
    const [configs, setConfigs] = useState([]);
    useEffect(() => {
        fetch('/api/admin/')
            .then(res => res.json())
            .then(data => setConfigs(data));
    }, []);
    const handleUpdate = async (key, newValue) => {
        setConfigs(configs.map(c => c.key === key ? { ...c, value: newValue } : c));
        await fetch(`/api/admin/${key}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: newValue })
        });
    };
    return (_jsx("div", { style: { padding: '2rem', background: '#f8fafc', flex: 1, overflowY: 'auto' }, children: _jsxs("div", { style: { maxWidth: '800px', margin: '0 auto', background: 'white', borderRadius: '8px', padding: '2rem', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }, children: [_jsx("h2", { style: { borderBottom: '2px solid #e2e8f0', paddingBottom: '0.5rem', marginBottom: '1.5rem', color: '#0f172a' }, children: "Enterprise Settings Control Center" }), _jsx("div", { style: { display: 'flex', flexDirection: 'column', gap: '1.5rem' }, children: configs.map(config => (_jsxs("div", { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: '#f1f5f9', borderRadius: '6px' }, children: [_jsxs("div", { style: { flex: 1 }, children: [_jsx("div", { style: { fontWeight: 600, color: '#1e293b' }, children: config.key }), _jsx("div", { style: { fontSize: '0.85rem', color: '#64748b' }, children: config.description })] }), _jsx("div", { style: { width: '200px' }, children: config.type === 'boolean' ? (_jsxs("select", { value: config.value, onChange: e => handleUpdate(config.key, e.target.value), style: { width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #cbd5e1' }, children: [_jsx("option", { value: "true", children: "Enabled" }), _jsx("option", { value: "false", children: "Disabled" })] })) : (_jsx("input", { type: config.is_sensitive ? 'password' : 'text', value: config.value, onChange: e => handleUpdate(config.key, e.target.value), style: { width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #cbd5e1' } })) })] }, config.key))) })] }) }));
}
function MainApp() {
    const [activeView, setActiveView] = useState('dashboard');
    return (_jsxs("div", { style: { display: 'flex', height: '100vh', flexDirection: 'column', fontFamily: 'Inter, sans-serif' }, children: [_jsxs("header", { style: { background: '#1e293b', color: 'white', padding: '1rem 1.5rem', display: 'flex', alignItems: 'center' }, children: [_jsx("h1", { style: { margin: 0, fontSize: '1.3rem', fontWeight: 600, flex: 1 }, children: "GeoSpatial Transport Intelligence" }), _jsxs("div", { style: { display: 'flex', gap: '1.5rem', marginRight: '2rem' }, children: [_jsx("button", { onClick: () => setActiveView('dashboard'), style: { background: 'transparent', border: 'none', color: activeView === 'dashboard' ? '#60a5fa' : 'white', fontWeight: 600, cursor: 'pointer', fontSize: '1rem' }, children: "Live Map" }), _jsx("button", { onClick: () => setActiveView('settings'), style: { background: 'transparent', border: 'none', color: activeView === 'settings' ? '#60a5fa' : 'white', fontWeight: 600, cursor: 'pointer', fontSize: '1rem' }, children: "Settings" })] }), activeView === 'dashboard' && (_jsxs("div", { style: { display: 'flex', gap: '1rem', fontSize: '0.9rem' }, children: [_jsxs("span", { style: { display: 'flex', alignItems: 'center', gap: '0.4rem' }, children: [_jsx("div", { style: { width: 12, height: 12, background: '#e74c3c', borderRadius: '50%' } }), " High Risk"] }), _jsxs("span", { style: { display: 'flex', alignItems: 'center', gap: '0.4rem' }, children: [_jsx("div", { style: { width: 12, height: 12, background: '#e67e22', borderRadius: '50%' } }), " Probable"] }), _jsxs("span", { style: { display: 'flex', alignItems: 'center', gap: '0.4rem' }, children: [_jsx("div", { style: { width: 12, height: 12, background: '#f1c40f', borderRadius: '50%' } }), " Potential"] }), _jsxs("span", { style: { display: 'flex', alignItems: 'center', gap: '0.4rem' }, children: [_jsx("div", { style: { width: 12, height: 12, background: '#95a5a6', borderRadius: '50%' } }), " Uncertain"] })] }))] }), activeView === 'dashboard' ? _jsx(Dashboard, {}) : _jsx(AdminSettings, {})] }));
}
export default function App() {
    return (_jsx(ErrorBoundary, { children: _jsx(MainApp, {}) }));
}
//# sourceMappingURL=App.js.map