document.getElementById('lat').addEventListener('change', () => {
    const lat = document.getElementById('lat').value;
    const lon = document.getElementById('lon').value;
    
    if (lat && lon && !isNaN(lat) && !isNaN(lon)) {
        if (map) {
            const pos = { lat: parseFloat(lat), lng: parseFloat(lon) };
            map.setCenter(pos);
            marker.setPosition(pos);
            updateAddressFromCoords(parseFloat(lat), parseFloat(lon));
        } else {
            initMap(lat, lon);
        }
    }
});

document.getElementById('lon').addEventListener('change', () => {
    const lat = document.getElementById('lat').value;
    const lon = document.getElementById('lon').value;
    
    if (lat && lon && !isNaN(lat) && !isNaN(lon)) {
        if (map) {
            const pos = { lat: parseFloat(lat), lng: parseFloat(lon) };
            map.setCenter(pos);
            marker.setPosition(pos);
            updateAddressFromCoords(parseFloat(lat), parseFloat(lon));
        } else {
            initMap(lat, lon);
        }
    }
});


let map;
let marker;
let autocomplete;
let geocoder;

// Initialize map



function initMap(lat, lon) {
    try {
        console.log('Initializing map with:', lat, lon);
        const position = { lat: parseFloat(lat), lng: parseFloat(lon) };
        
        map = new google.maps.Map(document.getElementById("map"), {
            zoom: 15,
            center: position,
        });
        
        marker = new google.maps.Marker({
            position: position,
            map: map,
            draggable: true
        });
        
        // Update address when marker is dragged
        marker.addListener('dragend', (event) => {
            const lat = event.latLng.lat();
            const lon = event.latLng.lng();
            document.getElementById('lat').value = lat;
            document.getElementById('lon').value = lon;
            updateAddressFromCoords(lat, lon);
        });
        
        // Update address when map is clicked
        map.addListener('click', (event) => {
            const lat = event.latLng.lat();
            const lon = event.latLng.lng();
            marker.setPosition(event.latLng);
            document.getElementById('lat').value = lat;
            document.getElementById('lon').value = lon;
            updateAddressFromCoords(lat, lon);
        });
        
        console.log('Map initialized successfully');
        
        // REMOVE THIS LINE:
        // updateAddressFromCoords(lat, lon);
        
    } catch (error) {
        console.error('Error initializing map:', error);
        document.getElementById('error').textContent = 'Error initializing map: ' + error.message;
    }
}
// Reverse geocoding - get address from coordinates


// Reverse geocoding - get address from coordinates
function updateAddressFromCoords(lat, lng) {
    // Don't try to geocode if coordinates are empty or invalid
    if (!lat || !lng || isNaN(lat) || isNaN(lng)) {
        console.log('Skipping geocoding - invalid coordinates');
        return;
    }
    
    if (!geocoder) {
        geocoder = new google.maps.Geocoder();
    }
    
    console.log('Getting address for:', lat, lng);
    
    // Add a small delay to avoid rate limiting
    setTimeout(() => {
        geocoder.geocode({ 
            location: { lat: parseFloat(lat), lng: parseFloat(lng) }
        }, (results, status) => {
            console.log('Geocode status:', status);
            
            if (status === 'OK' && results && results[0]) {
                document.getElementById('address').value = results[0].formatted_address;
                console.log('Address updated to:', results[0].formatted_address);
                document.getElementById('error').textContent = '';
            } else if (status === 'REQUEST_DENIED') {
                console.error('Geocoding request denied - check API key permissions and billing');
                document.getElementById('error').textContent = 'Geocoding denied - check billing is enabled in Google Cloud';
            } else {
                console.warn('Geocoding failed:', status);
                document.getElementById('error').textContent = 'Could not get address: ' + status;
            }
        });
    }, 300);
}

function initAutocomplete() {
    try {
        console.log('Initializing autocomplete');
        const input = document.getElementById('address');
        
        autocomplete = new google.maps.places.Autocomplete(input, {
		types: ['address'],
		componentRestrictions: { country: 'au' },
            	fields: ['formatted_address', 'geometry', 'name']
        });
        
        autocomplete.addListener('place_changed', () => {
            const place = autocomplete.getPlace();
            
            console.log('Place selected:', place);
            
            if (!place.geometry || !place.geometry.location) {
                alert("No details available for input: '" + place.name + "'");
                return;
            }
            
            const lat = place.geometry.location.lat();
            const lon = place.geometry.location.lng();
            
            document.getElementById('address').value = place.formatted_address || place.name;
            document.getElementById('lat').value = lat;
            document.getElementById('lon').value = lon;
            
            if (map) {
                const pos = { lat: lat, lng: lon };
                map.setCenter(pos);
                marker.setPosition(pos);
            } else {
                initMap(lat, lon);
            }
        });
        console.log('Autocomplete initialized successfully');
    } catch (error) {
        console.error('Error initializing autocomplete:', error);
        document.getElementById('error').textContent = 'Error initializing autocomplete: ' + error.message;
    }
}

function loadMapScript() {
    console.log('Loading map script...');
    fetch('/api/get_maps_api_key')
        .then(response => response.json())
        .then(data => {
            console.log('API key received, loading Google Maps...');
            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=${data.api_key}&libraries=places&callback=onMapScriptLoaded`;
            script.async = true;
            script.defer = true;
            script.onerror = (error) => {
                console.error('Failed to load Google Maps script:', error);
                document.getElementById('error').textContent = 'Failed to load Google Maps. Check console for details.';
            };
            document.head.appendChild(script);
        })
        .catch(error => {
            console.error('Error fetching API key:', error);
            document.getElementById('error').textContent = 'Error fetching API key: ' + error.message;
        });
}

window.onMapScriptLoaded = function() {
    console.log('Google Maps script loaded successfully');
    try {
        if (typeof google === 'undefined') {
            throw new Error('Google Maps object not found');
        }
        
        // Initialize geocoder
        geocoder = new google.maps.Geocoder();
        
        // Initialize autocomplete
        initAutocomplete();
        
        // Initialize map with default location (Sydney, for example)
        // You can change this to any default location
        initMap(-33.8688, 151.2093);
        
    } catch (error) {
        console.error('Error in onMapScriptLoaded:', error);
        document.getElementById('error').textContent = 'Error loading Google Maps: ' + error.message;
    }
};

// Get My Location button
document.getElementById('getLocationBtn').addEventListener('click', () => {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            position => {
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;
                
                console.log('Got user location:', lat, lon);
                
                document.getElementById('lat').value = lat;
                document.getElementById('lon').value = lon;
                
                // Update map
                const pos = { lat: lat, lng: lon };
                map.setCenter(pos);
                marker.setPosition(pos);
                
                // Update address from coordinates
                updateAddressFromCoords(lat, lon);
            },
            error => {
                alert('Error getting location: ' + error.message);
                console.error('Geolocation error:', error);
            }
        );
    } else {
        alert('Geolocation is not supported by your browser');
    }
});

loadMapScript();
