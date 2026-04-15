"""
API client for fetching real flight data from flights-api.creativeshrimp.dev
"""
import requests
import time
import os
import json
from typing import Optional, Dict, Any, List, Callable
import logging

# Try to import diskcache for persistent caching
try:
    import diskcache
    DISKCACHE_AVAILABLE = True
except ImportError:
    DISKCACHE_AVAILABLE = False

logger = logging.getLogger(__name__)


class FlightDataAPIClient:
    """Client for fetching real flight data from the Creative Shrimp API"""

    BASE_URL = "https://flights-api.creativeshrimp.dev/flights"

    # Timeout configuration (in seconds)
    DEFAULT_TIMEOUT = 30  # Standard requests (was 15)
    ARTCC_TIMEOUT = 60    # ARTCC requests need longer (was 30)

    # Progressive timeout multipliers for retries
    TIMEOUT_MULTIPLIERS = [1.0, 1.5, 2.0]  # 30s, 45s, 60s for standard

    def __init__(self, cache_timeout: int = 3600, cache_dir: Optional[str] = None):
        """
        Initialize the API client

        Args:
            cache_timeout: How long to cache results in seconds (default: 1 hour)
            cache_dir: Directory for persistent disk cache (default: user's app data)
        """
        self.cache_timeout = cache_timeout

        # In-memory cache as fallback
        self.memory_cache: Dict[str, tuple] = {}

        # Set up persistent disk cache
        self.disk_cache = None
        if DISKCACHE_AVAILABLE:
            try:
                if cache_dir is None:
                    # Use a sensible default cache directory
                    cache_dir = os.path.join(
                        os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                        'SSG', 'flight_cache'
                    )
                os.makedirs(cache_dir, exist_ok=True)
                self.disk_cache = diskcache.Cache(
                    cache_dir,
                    size_limit=500 * 1024 * 1024  # 500MB max cache size
                )
                logger.info(f"Disk cache initialized at: {cache_dir}")
            except Exception as e:
                logger.warning(f"Failed to initialize disk cache, using memory cache: {e}")
                self.disk_cache = None
        else:
            logger.info("diskcache not installed, using memory cache only")

        # Set up requests session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'Accept-Encoding': 'gzip, deflate',  # Ready for when server supports compression
            'Connection': 'keep-alive',
            'Accept': 'application/json'
        })

        # Configure connection pool size
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0  # We handle retries ourselves
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    @staticmethod
    def _strip_procedure_numbers(procedure: str) -> str:
        """
        Strip numeric suffixes from procedure names (e.g., 'EAGUL6' -> 'EAGUL')

        Args:
            procedure: Procedure name with optional numeric suffix

        Returns:
            Procedure name without numeric suffix
        """
        import re
        # Remove trailing digits from procedure name
        return re.sub(r'\d+$', '', procedure)

    @staticmethod
    def _format_procedures_for_api(procedures: Optional[List[str]]) -> Optional[str]:
        """
        Format a list of procedures for API query parameter ('+' separator, requests will URL-encode)

        Args:
            procedures: List of procedure names (with or without numbers)

        Returns:
            '+'-separated string of procedures without numbers, or None if empty
        """
        if not procedures:
            return None

        # Strip numbers from all procedures and join with '+'
        # requests.get() will URL-encode this to '%2B' automatically
        stripped_procs = [FlightDataAPIClient._strip_procedure_numbers(proc) for proc in procedures]
        # Remove any empty strings and duplicates
        stripped_procs = list(dict.fromkeys([p for p in stripped_procs if p]))

        return '+'.join(stripped_procs) if stripped_procs else None

    def _calculate_cruise_speed(self, aircraft_type: str) -> int:
        """
        Return default cruise speed fallback (used only when API doesn't provide speed)

        Args:
            aircraft_type: Aircraft type with optional equipment suffix (e.g., "B738")

        Returns:
            Cruise speed in knots (default: 450 for jets)
        """
        # Simple fallback - API should provide actual cruise speeds
        logger.debug(f"Using default cruise speed fallback for: {aircraft_type}")
        return 450

    def _get_cached(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get data from cache (disk cache first, then memory cache)

        Args:
            cache_key: The cache key to look up

        Returns:
            Cached data if valid, None otherwise
        """
        # Try disk cache first
        if self.disk_cache is not None:
            try:
                cached = self.disk_cache.get(cache_key)
                if cached is not None:
                    cached_data, timestamp = cached
                    if time.time() - timestamp < self.cache_timeout:
                        logger.debug(f"Disk cache hit for {cache_key}")
                        return cached_data
            except Exception as e:
                logger.warning(f"Error reading from disk cache: {e}")

        # Fall back to memory cache
        if cache_key in self.memory_cache:
            cached_data, timestamp = self.memory_cache[cache_key]
            if time.time() - timestamp < self.cache_timeout:
                logger.debug(f"Memory cache hit for {cache_key}")
                return cached_data

        return None

    def _set_cached(self, cache_key: str, data: List[Dict[str, Any]]) -> None:
        """
        Store data in cache (both disk and memory)

        Args:
            cache_key: The cache key
            data: The data to cache
        """
        timestamp = time.time()

        # Store in memory cache
        self.memory_cache[cache_key] = (data, timestamp)

        # Store in disk cache
        if self.disk_cache is not None:
            try:
                self.disk_cache.set(cache_key, (data, timestamp), expire=self.cache_timeout)
            except Exception as e:
                logger.warning(f"Error writing to disk cache: {e}")

    @property
    def cache(self) -> Dict[str, tuple]:
        """Backwards-compatible access to memory cache"""
        return self.memory_cache

    def fetch_flights(
        self,
        departure: Optional[str] = None,
        arrival: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        retries: int = 3,
        depproc: Optional[str] = None,
        arrproc: Optional[str] = None,
        wakecat: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch flights from the API

        Args:
            departure: Departure airport ICAO code (use "any" for all departures)
            arrival: Arrival airport ICAO code (use "any" for all arrivals)
            limit: Maximum number of flights to request (server-side limit)
            offset: Pagination offset for fetching subsequent pages
            retries: Number of retries if request fails
            depproc: URL-encoded departure procedures filter (e.g., 'EAGUL%2BZZULU')
            arrproc: URL-encoded arrival procedures filter (e.g., 'STAR1%2BSTAR2')
            wakecat: Server-side wake category filter: 'L', 'M', or 'H'.
                     Lets small airports with few heavies actually return the
                     heavies we care about (rather than diluting them in an
                     overwhelmingly medium pool).
            progress_callback: Optional callback function for progress updates

        Returns:
            Dictionary with 'flights' list and 'pagination' info (offset, hasMore),
            or None if request fails
        """
        # Build cache key (include offset for pagination)
        dep = departure or "any"
        arr = arrival or "any"
        dep_proc = depproc or "none"
        arr_proc = arrproc or "none"
        wake = (wakecat or "any").upper() if wakecat else "any"
        cache_key = f"{dep}:{arr}:{limit}:{offset}:{dep_proc}:{arr_proc}:{wake}"

        # Check cache (disk and memory)
        cached_data = self._get_cached(cache_key)
        if cached_data is not None:
            logger.debug(f"Using cached data for {cache_key}")
            return cached_data

        # Build request parameters - use server-side limit and offset
        params = {
            'limit': limit,
            'offset': offset
        }
        if departure:
            params['departure'] = departure
        if arrival:
            params['arrival'] = arrival
        if depproc:
            params['depproc'] = depproc
        if arrproc:
            params['arrproc'] = arrproc
        if wakecat:
            params['wakecat'] = wakecat.upper()

        # Try to fetch from API with progressive timeouts
        for attempt in range(retries):
            try:
                # Calculate timeout with progressive increase
                multiplier = self.TIMEOUT_MULTIPLIERS[min(attempt, len(self.TIMEOUT_MULTIPLIERS) - 1)]
                timeout = int(self.DEFAULT_TIMEOUT * multiplier)

                # Log all parameters including procedures
                log_msg = f"Fetching flights: departure={dep}, arrival={arr}, limit={limit}"
                if depproc:
                    log_msg += f", depproc={depproc}"
                if arrproc:
                    log_msg += f", arrproc={arrproc}"
                if wakecat:
                    log_msg += f", wakecat={wakecat.upper()}"
                log_msg += f" (attempt {attempt + 1}/{retries}, timeout={timeout}s)"
                logger.info(log_msg)

                # Notify progress callback
                if progress_callback:
                    progress_callback(f"Fetching {dep} → {arr} (attempt {attempt + 1}/{retries})...")

                # Log the full URL for debugging
                logger.debug(f"API URL: {self.BASE_URL}, params: {params}")

                # Use session for connection pooling, stream for large responses
                start_time = time.time()
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=timeout,
                    stream=True  # Stream response to handle large payloads
                )

                if response.status_code == 200:
                    # Stream and parse response
                    elapsed = time.time() - start_time
                    if progress_callback:
                        progress_callback(f"Downloading data... ({elapsed:.1f}s)")

                    # Read streamed content
                    content = response.content
                    data = json.loads(content)

                    # Validate response structure
                    if not isinstance(data, dict) or 'success' not in data:
                        logger.error(f"Invalid API response structure: {data}")
                        return None

                    if not data.get('success'):
                        logger.warning(f"API returned success=false: {data}")
                        return None

                    # Extract flight data (server already applies limit)
                    flights = data.get('data', [])

                    # Extract pagination info
                    pagination = data.get('pagination', {'offset': offset, 'hasMore': False})

                    if not flights:
                        logger.warning(f"No flights found for {dep} -> {arr}")
                        result = {'flights': [], 'pagination': pagination}
                        self._set_cached(cache_key, result)
                        return result

                    elapsed = time.time() - start_time
                    logger.info(f"Fetched {len(flights)} flights from API ({dep} -> {arr}) in {elapsed:.1f}s, hasMore={pagination.get('hasMore', False)}")

                    # Build result with pagination info
                    result = {
                        'flights': flights,
                        'pagination': pagination
                    }

                    # Cache the result (both disk and memory)
                    self._set_cached(cache_key, result)

                    return result

                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    if progress_callback:
                        progress_callback(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"API returned status code {response.status_code}")
                    if attempt < retries - 1:
                        time.sleep(1)

            except requests.exceptions.Timeout:
                elapsed = time.time() - start_time if 'start_time' in locals() else 0
                logger.error(f"Request timeout after {elapsed:.1f}s (attempt {attempt + 1}/{retries})")
                if progress_callback:
                    progress_callback(f"Timeout, retrying with longer timeout...")
                if attempt < retries - 1:
                    time.sleep(2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error fetching flights (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2)
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Error parsing API response (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error fetching flights (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)

        logger.error(f"Failed to fetch flights after {retries} attempts")
        return None

    def fetch_departures(
        self,
        airport_icao: str,
        limit: int = 200,
        sids: Optional[List[str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch departures from a specific airport, optionally filtered by SIDs

        Args:
            airport_icao: Airport ICAO code
            limit: Maximum number of flights to fetch
            sids: Optional list of SID names to filter by (numbers will be stripped automatically)

        Returns:
            List of departure flight dictionaries or None if request fails
        """
        # Format SIDs for API if provided
        depproc = self._format_procedures_for_api(sids)

        result = self.fetch_flights(
            departure=airport_icao,
            arrival=None,
            limit=limit,
            depproc=depproc
        )
        # Extract flights list for backwards compatibility
        if result is None:
            return None
        return result.get('flights', [])

    def fetch_arrivals(
        self,
        airport_icao: str,
        limit: int = 200,
        stars: Optional[List[str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch arrivals to a specific airport, optionally filtered by STARs

        Args:
            airport_icao: Airport ICAO code
            limit: Maximum number of flights to fetch
            stars: Optional list of STAR names to filter by (numbers will be stripped automatically)

        Returns:
            List of arrival flight dictionaries or None if request fails
        """
        # Format STARs for API if provided
        arrproc = self._format_procedures_for_api(stars)

        result = self.fetch_flights(
            departure=None,
            arrival=airport_icao,
            limit=limit,
            arrproc=arrproc
        )
        # Extract flights list for backwards compatibility
        if result is None:
            return None
        return result.get('flights', [])

    def fetch_artcc_flights(
        self,
        artcc_id: str,
        limit: int = 1000,
        offset: int = 0,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch flights within a specific ARTCC

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB", "ZLA")
            limit: Maximum number of flights to fetch (server-side limit)
            offset: Pagination offset for fetching subsequent pages
            progress_callback: Optional callback function for progress updates

        Returns:
            Dictionary with 'flights' list and 'pagination' info (offset, hasMore),
            or None if request fails
        """
        # Build cache key (include offset for pagination)
        cache_key = f"artcc:{artcc_id}:{limit}:{offset}"

        # Check cache (disk and memory)
        cached_data = self._get_cached(cache_key)
        if cached_data is not None:
            logger.debug(f"Using cached data for ARTCC {artcc_id}")
            return cached_data

        # Build request parameters with ARTCC (prefix with K) and pagination
        params = {
            'artcc': f"K{artcc_id.upper()}",
            'limit': limit,
            'offset': offset
        }

        # Try to fetch from API with progressive timeouts
        retries = 3
        for attempt in range(retries):
            try:
                # Calculate timeout with progressive increase (using ARTCC timeout)
                multiplier = self.TIMEOUT_MULTIPLIERS[min(attempt, len(self.TIMEOUT_MULTIPLIERS) - 1)]
                timeout = int(self.ARTCC_TIMEOUT * multiplier)

                logger.info(f"Fetching flights for ARTCC {artcc_id}, limit={limit} (attempt {attempt + 1}/{retries}, timeout={timeout}s)")
                logger.debug(f"API URL: {self.BASE_URL}, params: {params}")

                # Notify progress callback
                if progress_callback:
                    progress_callback(f"Fetching ARTCC {artcc_id} flights (attempt {attempt + 1}/{retries})...")

                # Use session for connection pooling, stream for large responses
                start_time = time.time()
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=timeout,
                    stream=True
                )

                if response.status_code == 200:
                    # Stream and parse response
                    elapsed = time.time() - start_time
                    if progress_callback:
                        progress_callback(f"Downloading ARTCC data... ({elapsed:.1f}s)")

                    content = response.content
                    data = json.loads(content)

                    # Validate response structure
                    if not isinstance(data, dict) or 'success' not in data:
                        logger.error(f"Invalid API response structure: {data}")
                        return None

                    if not data.get('success'):
                        logger.warning(f"API returned success=false: {data}")
                        return None

                    # Extract flight data (server already applies limit)
                    flights = data.get('data', [])

                    # Extract pagination info
                    pagination = data.get('pagination', {'offset': offset, 'hasMore': False})

                    if not flights:
                        logger.warning(f"No flights found for ARTCC {artcc_id}")
                        result = {'flights': [], 'pagination': pagination}
                        self._set_cached(cache_key, result)
                        return result

                    elapsed = time.time() - start_time
                    logger.info(f"Fetched {len(flights)} flights for ARTCC {artcc_id} in {elapsed:.1f}s, hasMore={pagination.get('hasMore', False)}")

                    # Build result with pagination info
                    result = {
                        'flights': flights,
                        'pagination': pagination
                    }

                    # Cache the result (both disk and memory)
                    self._set_cached(cache_key, result)

                    return result

                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    if progress_callback:
                        progress_callback(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"API returned status code {response.status_code}")
                    if attempt < retries - 1:
                        time.sleep(1)

            except requests.exceptions.Timeout:
                elapsed = time.time() - start_time if 'start_time' in locals() else 0
                logger.error(f"Request timeout after {elapsed:.1f}s (attempt {attempt + 1}/{retries})")
                if progress_callback:
                    progress_callback(f"Timeout, retrying with longer timeout...")
                if attempt < retries - 1:
                    time.sleep(2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error fetching ARTCC flights (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2)
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Error parsing API response (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error fetching ARTCC flights (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)

        logger.error(f"Failed to fetch ARTCC flights after {retries} attempts")
        return None

    def fetch_all_flights(
        self,
        departure: Optional[str] = None,
        arrival: Optional[str] = None,
        max_flights: int = 1000,
        page_size: int = 200,
        retries: int = 3,
        depproc: Optional[str] = None,
        arrproc: Optional[str] = None,
        wakecat: Optional[str] = None,
        start_offset: int = 0,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch all flights using automatic pagination

        Args:
            departure: Departure airport ICAO code (use "any" for all departures)
            arrival: Arrival airport ICAO code (use "any" for all arrivals)
            max_flights: Maximum total number of flights to fetch across all pages
            page_size: Number of flights to fetch per API request
            retries: Number of retries if request fails
            depproc: URL-encoded departure procedures filter
            arrproc: URL-encoded arrival procedures filter
            wakecat: Server-side wake category filter ('L', 'M', 'H').
            progress_callback: Optional callback function for progress updates

        Returns:
            List of all flight dictionaries, or None if request fails
        """
        all_flights = []
        offset = max(0, int(start_offset))

        while len(all_flights) < max_flights:
            # Calculate limit for this page
            remaining = max_flights - len(all_flights)
            limit = min(page_size, remaining)

            if progress_callback:
                progress_callback(f"Fetching flights {offset + 1}-{offset + limit}...")

            result = self.fetch_flights(
                departure=departure,
                arrival=arrival,
                limit=limit,
                offset=offset,
                retries=retries,
                depproc=depproc,
                arrproc=arrproc,
                wakecat=wakecat,
                progress_callback=progress_callback
            )

            if result is None:
                # Request failed
                if all_flights:
                    # Return what we have so far
                    logger.warning(f"Pagination stopped early, returning {len(all_flights)} flights")
                    return all_flights
                return None

            flights = result.get('flights', [])
            pagination = result.get('pagination', {})

            all_flights.extend(flights)
            offset += len(flights)

            # Check if there are more pages
            if not pagination.get('hasMore', False) or not flights:
                break

        logger.info(
            f"Fetched {len(all_flights)} flights via pagination "
            f"(start_offset={start_offset})"
        )
        return all_flights

    def fetch_all_artcc_flights(
        self,
        artcc_id: str,
        max_flights: int = 2000,
        page_size: int = 500,
        start_offset: int = 0,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch all flights for an ARTCC using automatic pagination

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB", "ZLA")
            max_flights: Maximum total number of flights to fetch across all pages
            page_size: Number of flights to fetch per API request
            progress_callback: Optional callback function for progress updates

        Returns:
            List of all flight dictionaries, or None if request fails
        """
        all_flights = []
        offset = max(0, int(start_offset))

        while len(all_flights) < max_flights:
            # Calculate limit for this page
            remaining = max_flights - len(all_flights)
            limit = min(page_size, remaining)

            if progress_callback:
                progress_callback(f"Fetching ARTCC {artcc_id} flights {offset + 1}-{offset + limit}...")

            result = self.fetch_artcc_flights(
                artcc_id=artcc_id,
                limit=limit,
                offset=offset,
                progress_callback=progress_callback
            )

            if result is None:
                # Request failed
                if all_flights:
                    # Return what we have so far
                    logger.warning(f"Pagination stopped early, returning {len(all_flights)} ARTCC flights")
                    return all_flights
                return None

            flights = result.get('flights', [])
            pagination = result.get('pagination', {})

            all_flights.extend(flights)
            offset += len(flights)

            # Check if there are more pages
            if not pagination.get('hasMore', False) or not flights:
                break

        logger.info(
            f"Fetched {len(all_flights)} flights for ARTCC {artcc_id} "
            f"(start_offset={start_offset})"
        )
        return all_flights

    def clear_cache(self):
        """Clear all cached flight data (both disk and memory)"""
        self.memory_cache.clear()
        if self.disk_cache is not None:
            try:
                self.disk_cache.clear()
                logger.info("Disk and memory cache cleared")
            except Exception as e:
                logger.warning(f"Error clearing disk cache: {e}")
                logger.info("Memory cache cleared")
        else:
            logger.info("Memory cache cleared")
