from mcp.server.fastmcp import FastMCP
import json
import httpx
import os
from datetime import datetime
import webbrowser
import tempfile
from pathlib import Path
import asyncio
import math
import requests
from typing import Tuple

# 설정값
# FOREST_FIRE_DATA_PATH = "./forest_fire_data.json"
FOREST_FIRE_DATA_PATH = "C:/Users/user/Desktop/MCP/forest_fire_data.json"
KAKAO_API_KEY = "5d220d9b53f82695f5956d037a76e990"  # 카카오 API 키 (JavaScript 키)
KAKAO_MAP_API_KEY = KAKAO_API_KEY  # 지도 API용 키 (JavaScript 키)
KAKAO_REST_API_KEY = "9c5b23bb9469f5cb90d683af667e3d82"  # 카카오 REST API 키 (주소 검색용)

mcp = FastMCP("산불정보 시각화 MCP 서버")

# TM 좌표를 WGS84(경위도)로 변환하는 함수 (대략적인 변환)
def tm_to_wgs84_approx(tm_x: float, tm_y: float) -> Tuple[float, float]:
    """TM 좌표를 WGS84 좌표로 근사 변환합니다.
    
    Args:
        tm_x: TM 좌표계의 X 좌표
        tm_y: TM 좌표계의 Y 좌표
        
    Returns:
        (경도, 위도) 튜플 (WGS84)
    """
    try:
        # 국내 TM 좌표를 WGS84로 대략적 변환 (선형 근사)
        # 이 값들은 대략적인 스케일 및 오프셋 값으로, 정확한 변환이 아님
        lng = tm_x * 0.000009 + 126.0
        lat = tm_y * 0.000009 + 32.0
        
        # 좌표 범위 검증 (대한민국 영역: 대략 125~132, 33~43)
        if 125 <= lng <= 132 and 33 <= lat <= 43:
            return (lng, lat)
        
        # 범위를 벗어나면 다른 계수로 다시 시도
        lng = tm_x * 0.0000025 + 126.7
        lat = tm_y * 0.0000025 + 36.5
        
        if 125 <= lng <= 132 and 33 <= lat <= 43:
            return (lng, lat)
    except Exception as e:
        print(f"좌표 근사 변환 오류: {e}")
    
    # 모든 변환 실패 시 임의의 유효 좌표 반환 (강원도 고성 부근)
    print(f"좌표 변환 최종 실패: ({tm_x}, {tm_y}) -> 기본값 사용")
    return (128.4677, 38.3806)

# 지역 이름으로 좌표를 검색하는 함수
async def search_location_by_name(location_name: str) -> Tuple[float, float]:
    """지역명을 기반으로 중심 좌표를 검색합니다.
    
    Args:
        location_name: 검색할 지역명
        
    Returns:
        (경도, 위도) 튜플
    """
    try:
        url = f"https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
        params = {"query": location_name}
        
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if "documents" in data and data["documents"]:
            x = float(data["documents"][0]["x"])
            y = float(data["documents"][0]["y"])
            return (x, y)
    except Exception as e:
        print(f"지역 검색 오류: {e}")
    
    # 검색 실패 시 기본값 (강원도 고성 부근)
    return (128.4677, 38.3806)

# 데이터 로드 함수
def load_forest_fire_data():
    if os.path.exists(FOREST_FIRE_DATA_PATH):
        try:
            with open(FOREST_FIRE_DATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return {"error": f"데이터 로드 중 오류 발생: {str(e)}"}
    else:
        return {"error": f"데이터 파일이 존재하지 않습니다: {FOREST_FIRE_DATA_PATH}\nforest_fire_data.py를 실행하여 데이터를 준비해주세요."}

# 산불 데이터의 좌표계를 변환하고 캐싱하는 함수
@mcp.tool()
async def convert_coordinates_batch(count: int = 10) -> str:
    """산불 데이터의 TM 좌표계를 WGS84 좌표계로 변환합니다
    
    Args:
        count: 변환할 데이터 개수 (기본값: 10, 최대: 100)
    
    Returns:
        변환 결과 메시지
    """
    data = load_forest_fire_data()
    if isinstance(data, dict) and "error" in data:
        return data["error"]
    
    # 변환할 최대 개수 제한
    max_count = min(count, 100)
    
    # 캐시 파일 경로
    cache_file = "C:/Users/user/Desktop/MCP/coordinate_cache.json"
    
    # 기존 캐시 로드
    cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception as e:
            return f"캐시 파일 로드 중 오류 발생: {str(e)}"
    
    # 변환 작업
    converted_count = 0
    for item in data:
        # 이미 WGS84 좌표가 있거나 캐시에 있는 경우 스킵
        item_key = f"{item.get('location')}_{item.get('fire_date')}"
        if item_key in cache:
            if "wgs84" not in item:
                item["wgs84"] = cache[item_key]
            converted_count += 1
            continue
            
        # 좌표 정보가 없는 경우 스킵
        if "coordinates" not in item or len(item["coordinates"]) != 2:
            continue
            
        # 변환할 개수 제한 확인
        if converted_count >= max_count:
            break
            
        # TM 좌표를 WGS84 좌표로 변환
        x, y = item["coordinates"]
        lng, lat = tm_to_wgs84_approx(x, y)
        
        if lng is not None and lat is not None:
            item["wgs84"] = [lng, lat]
            cache[item_key] = [lng, lat]
            converted_count += 1
        
        # API 호출 제한을 위한 딜레이
        await asyncio.sleep(0.2)
    
    # 캐시 저장
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        return f"캐시 파일 저장 중 오류 발생: {str(e)}"
    
    # 변환된 데이터 저장
    try:
        with open(FOREST_FIRE_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"데이터 파일 저장 중 오류 발생: {str(e)}"
    
    return f"좌표계 변환 완료: 총 {converted_count}개의 좌표가 변환되었습니다."

# 지역 이름으로 좌표를 검색하는 함수
@mcp.tool()
async def search_location(location: str) -> str:
    """지역 이름으로 좌표를 검색합니다
    
    Args:
        location: 검색할 지역 이름 (예: "강원도 고성군")
    
    Returns:
        검색 결과 메시지
    """
    lng, lat = await search_location_by_name(location)
    
    if lng is not None and lat is not None:
        return f"{location}의 좌표: 경도 {lng}, 위도 {lat}"
    else:
        return f"{location}의 좌표를 찾을 수 없습니다."

@mcp.resource("forest-fire://data")
def forest_fire_resource() -> str:
    """산불발생위치도 데이터를 리소스로 제공합니다"""
    data = load_forest_fire_data()
    if "error" in data:
        return data["error"]
    return json.dumps(data, ensure_ascii=False, indent=2)

@mcp.tool()
def get_forest_fire_data(province: str = None, year: str = None) -> str:
    """지정된 지역 및 연도에 따른 산불 발생 데이터를 제공합니다
    
    Args:
        province: 조회할 시/도 이름 (예: "경기도", "강원도")
        year: 조회할 연도 (예: "2020", "2021")
    
    Returns:
        해당 조건에 맞는 산불 발생 정보
    """
    data = load_forest_fire_data()
    if isinstance(data, dict) and "error" in data:
        return data["error"]
    
    # 데이터 필터링
    filtered_data = data
    
    if province:
        filtered_data = [item for item in filtered_data if province in item.get("location", "")]
    
    if year:
        filtered_data = [item for item in filtered_data if year in item.get("fire_date", "")]
    
    if not filtered_data:
        return f"조건에 맞는 산불 데이터가 없습니다. (지역: {province or '전체'}, 연도: {year or '전체'})"
    
    # 결과 포맷팅
    results = []
    for item in filtered_data[:10]:  # 최대 10개 항목만 표시
        location = item.get("location", "위치 정보 없음")
        fire_date = item.get("fire_date", "날짜 정보 없음")
        fire_size = item.get("fire_size", "크기 정보 없음")
        fire_cause = item.get("fire_cause", "원인 정보 없음")
        
        results.append(f"- 위치: {location}\n  날짜: {fire_date}\n  규모: {fire_size}\n  원인: {fire_cause}")
    
    total_count = len(filtered_data)
    displayed_count = min(10, total_count)
    
    if total_count > 10:
        results.append(f"\n※ 총 {total_count}건 중 {displayed_count}건만 표시됩니다.")
    
    return f"산불 발생 정보 (지역: {province or '전체'}, 연도: {year or '전체'}):\n\n" + "\n\n".join(results)

@mcp.tool()
def visualize_forest_fires(province: str = None, year: str = None) -> str:
    """지정된 지역 및 연도의 산불 발생 위치를 카카오맵에 시각화합니다
    
    Args:
        province: 조회할 시/도 이름 (예: "경기도", "강원도")
        year: 조회할 연도 (예: "2020", "2021")
    
    Returns:
        시각화 결과 메시지와 지도 URL
    """
    data = load_forest_fire_data()
    if isinstance(data, dict) and "error" in data:
        return data["error"]
    
    # 데이터 필터링
    filtered_data = data
    
    if province:
        filtered_data = [item for item in filtered_data if province in item.get("location", "")]
    
    if year:
        filtered_data = [item for item in filtered_data if year in item.get("fire_date", "")]
    
    if not filtered_data:
        return f"조건에 맞는 산불 데이터가 없습니다. (지역: {province or '전체'}, 연도: {year or '전체'})"
    
    # 최대 100개 데이터로 제한
    if len(filtered_data) > 100:
        filtered_data = filtered_data[:100]
    
    # HTML 파일 생성
    html_content = create_kakao_map_html(filtered_data, province, year)
    
    # 임시 HTML 파일 저장 및 열기
    with tempfile.NamedTemporaryFile(delete=False, suffix='.html', mode='w', encoding='utf-8') as f:
        f.write(html_content)
        temp_path = f.name
    
    # 브라우저에서 열기
    webbrowser.open('file://' + temp_path)
    
    return f"""산불 발생 위치를 카카오맵에 시각화했습니다.
지역: {province or '전체'}
연도: {year or '전체'}
데이터 수: {len(filtered_data)}개

브라우저에서 지도가 열렸습니다. 각 마커를 클릭하면 상세 정보를 확인할 수 있습니다."""

def create_kakao_map_html(data, province=None, year=None):
    """카카오맵 API를 사용하여 HTML 파일을 생성합니다"""
    
    # 중심점 계산 (모든 좌표의 평균)
    valid_coords = [item["coordinates"] for item in data if "coordinates" in item and len(item["coordinates"]) == 2]
    if not valid_coords:
        center_lat, center_lng = 36.5, 127.5  # 한국 중심 좌표 (기본값)
    else:
        center_lng = sum(coord[0] for coord in valid_coords) / len(valid_coords)
        center_lat = sum(coord[1] for coord in valid_coords) / len(valid_coords)
    
    # HTML 템플릿 작성
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>산불 발생 위치 지도 ({province or '전체'}, {year or '전체'})</title>
        <style>
            body, html {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
            }}
            #map {{
                width: 100%;
                height: 100%;
            }}
            .info-window {{
                padding: 10px;
                max-width: 300px;
            }}
            .info-window h3 {{
                margin-top: 0;
                margin-bottom: 10px;
            }}
            .info-window p {{
                margin: 5px 0;
            }}
            .info-window .label {{
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}"></script>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=clusterer"></script>
        <script>
            var mapContainer = document.getElementById('map'),
                mapOption = {{
                    center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                    level: 9
                }};
            
            var map = new kakao.maps.Map(mapContainer, mapOption);
            
            // 마커 클러스터러 생성
            var clusterer = new kakao.maps.MarkerClusterer({{
                map: map,
                averageCenter: true,
                minLevel: 5
            }});
            
            var markers = [];
            var positions = [
    """
    
    # 마커 데이터 추가
    for item in data:
        if "coordinates" not in item or len(item["coordinates"]) != 2:
            continue
            
        lng, lat = item["coordinates"]
        location = item.get("location", "위치 정보 없음").replace("'", "\\'")
        fire_date = item.get("fire_date", "날짜 정보 없음").replace("'", "\\'")
        fire_size = item.get("fire_size", "크기 정보 없음").replace("'", "\\'")
        fire_cause = item.get("fire_cause", "원인 정보 없음").replace("'", "\\'")
        
        html += f"""
                {{
                    position: new kakao.maps.LatLng({lat}, {lng}),
                    title: '{location}',
                    content: '<div class="info-window"><h3>{location}</h3>' +
                             '<p><span class="label">발생일:</span> {fire_date}</p>' +
                             '<p><span class="label">규모:</span> {fire_size}</p>' +
                             '<p><span class="label">원인:</span> {fire_cause}</p></div>'
                }},"""
    
    html += """
            ];
            
            // 마커 생성
            for (var i = 0; i < positions.length; i++) {
                var marker = new kakao.maps.Marker({
                    position: positions[i].position,
                    title: positions[i].title
                });
                
                markers.push(marker);
                
                // 인포윈도우 생성
                var infowindow = new kakao.maps.InfoWindow({
                    content: positions[i].content
                });
                
                // 마커에 클릭 이벤트 추가
                kakao.maps.event.addListener(marker, 'click', makeClickListener(map, marker, infowindow));
            }
            
            // 클릭 이벤트 리스너 생성 함수
            function makeClickListener(map, marker, infowindow) {
                return function() {
                    // 열려있는 모든 인포윈도우 닫기
                    for (var i = 0; i < markers.length; i++) {
                        if (markers[i].infowindow) {
                            markers[i].infowindow.close();
                        }
                    }
                    
                    infowindow.open(map, marker);
                    marker.infowindow = infowindow;
                };
            }
            
            // 마커 클러스터러에 마커 추가
            clusterer.addMarkers(markers);
        </script>
    </body>
    </html>
    """
    
    return html

@mcp.tool()
def get_forest_fire_stats() -> str:
    """산불 발생 통계 정보를 제공합니다"""
    data = load_forest_fire_data()
    if isinstance(data, dict) and "error" in data:
        return data["error"]
    
    # 통계 계산
    total_fires = len(data)
    
    # 연도별 집계
    years_count = {}
    # 지역별 집계
    regions_count = {}
    # 원인별 집계
    causes_count = {}
    
    for item in data:
        # 연도 추출
        fire_date = item.get("fire_date", "")
        year = fire_date[:4] if fire_date and len(fire_date) >= 4 else "알 수 없음"
        years_count[year] = years_count.get(year, 0) + 1
        
        # 지역 집계
        location = item.get("location", "알 수 없음")
        region = location.split()[0] if location and " " in location else location
        regions_count[region] = regions_count.get(region, 0) + 1
        
        # 원인 집계
        cause = item.get("fire_cause", "알 수 없음")
        causes_count[cause] = causes_count.get(cause, 0) + 1
    
    # 결과 포맷팅
    years_stats = "\n".join([f"- {year}: {count}건" for year, count in sorted(years_count.items()) if year != "알 수 없음"])
    regions_stats = "\n".join([f"- {region}: {count}건" for region, count in sorted(regions_count.items(), key=lambda x: x[1], reverse=True)[:5]])
    causes_stats = "\n".join([f"- {cause}: {count}건" for cause, count in sorted(causes_count.items(), key=lambda x: x[1], reverse=True) if cause != "알 수 없음"])
    
    return f"""산불 발생 통계 정보:

총 산불 발생 건수: {total_fires}건

연도별 발생 건수:
{years_stats}

지역별 발생 건수 (상위 5개):
{regions_stats}

원인별 발생 건수:
{causes_stats}
"""

@mcp.tool()
def analyze_forest_fire_risk(province: str) -> str:
    """특정 지역의 산불 위험도를 분석합니다
    
    Args:
        province: 분석할 시/도 이름 (예: "경기도", "강원도")
    
    Returns:
        해당 지역의 산불 위험도 분석 결과
    """
    if not province:
        return "지역을 지정해주세요."
        
    data = load_forest_fire_data()
    if isinstance(data, dict) and "error" in data:
        return data["error"]
    
    # 해당 지역 데이터 필터링
    region_data = [item for item in data if province in item.get("location", "")]
    
    if not region_data:
        return f"{province} 지역의 산불 데이터가 없습니다."
    
    # 연도별 발생 건수
    years_count = {}
    # 원인별 발생 건수
    causes_count = {}
    # 월별 발생 건수
    months_count = {}
    
    for item in region_data:
        # 연도 추출 (YYYYMMDDHHMM 형식)
        fire_date = item.get("fire_date", "")
        if fire_date and len(fire_date) >= 4:
            year = fire_date[:4]
            years_count[year] = years_count.get(year, 0) + 1
            
            # 월 추출 (YYYYMMDDHHMM 형식)
            if len(fire_date) >= 6:
                month = fire_date[4:6]
                months_count[month] = months_count.get(month, 0) + 1
        
        # 원인 집계 (빈 문자열이 아닌 경우에만)
        cause = item.get("fire_cause", "알 수 없음")
        if cause and cause != "알 수 없음":
            causes_count[cause] = causes_count.get(cause, 0) + 1
        else:
            causes_count["알 수 없음"] = causes_count.get("알 수 없음", 0) + 1
    
    # 최근 5년간 추세 확인 (데이터가 있는 경우)
    years = sorted(years_count.keys())
    recent_years = years[-5:] if len(years) >= 5 else years
    trend = ""
    if recent_years:
        counts = [years_count[year] for year in recent_years]
        if len(counts) >= 2:
            if counts[-1] > counts[0]:
                trend = f"최근 {len(recent_years)}년간 산불 발생이 증가하는 추세입니다."
            elif counts[-1] < counts[0]:
                trend = f"최근 {len(recent_years)}년간 산불 발생이 감소하는 추세입니다."
            else:
                trend = f"최근 {len(recent_years)}년간 산불 발생이 비슷한 수준을 유지하고 있습니다."
    
    # 주요 발생 원인 (최대 3개, 알 수 없음이 아닌 경우만)
    valid_causes = {k: v for k, v in causes_count.items() if k != "알 수 없음"}
    if not valid_causes:  # 유효한 원인이 없으면 모든 원인 포함
        valid_causes = causes_count
    
    top_causes = sorted(valid_causes.items(), key=lambda x: x[1], reverse=True)
    top_causes_text = "\n".join([f"- {cause}: {count}건" for cause, count in top_causes[:3]])
    
    # 월별 발생 패턴
    high_risk_months = sorted(months_count.items(), key=lambda x: x[1], reverse=True)
    months_korean = {
        "01": "1월", "02": "2월", "03": "3월", "04": "4월", "05": "5월", "06": "6월",
        "07": "7월", "08": "8월", "09": "9월", "10": "10월", "11": "11월", "12": "12월"
    }
    high_risk_months_text = ", ".join([months_korean.get(month, month) for month, _ in high_risk_months[:3]])
    
    # 위험도 평가
    total_fires = len(region_data)
    
    # 데이터가 있는 연도 수 계산 (0으로 나누는 것 방지)
    num_years = len(years_count)
    avg_fires_per_year = total_fires / max(num_years, 1)
    
    risk_level = "낮음"
    if avg_fires_per_year > 30:
        risk_level = "매우 높음"
    elif avg_fires_per_year > 20:
        risk_level = "높음"
    elif avg_fires_per_year > 10:
        risk_level = "중간"
    
    return f"""{province} 지역 산불 위험도 분석:

총 산불 발생 건수: {total_fires}건
연평균 발생 건수: {avg_fires_per_year:.1f}건 (총 {num_years}년 데이터 기준)
산불 발생 위험도: {risk_level}

주요 발생 원인:
{top_causes_text}

산불 발생 위험이 높은 시기: {high_risk_months_text}

{trend}

예방 권고사항:
1. 건조한 시기에 입산 시 화기 소지 금지
2. 농경지, 과수원 등 소각 작업 자제
3. 등산로 외 지역 출입 자제
4. 산림 인접 지역에서의 흡연 및 취사 금지
"""

@mcp.tool()
def get_forest_fire_safety_tips() -> str:
    """산불 예방 및 대처 요령을 제공합니다"""
    return """산불 예방 및 대처 요령:

[산불 예방법]
1. 입산 시 라이터, 성냥 등 화기물 소지 금지
2. 산림 내 흡연 금지 및 담배꽁초 완전 소화
3. 등산로 외 지역 출입 금지
4. 취사행위 및 모닥불 피우기 금지
5. 농촌에서 농업 부산물 소각 금지
6. 쓰레기 소각 금지
7. 논·밭두렁 및 농산폐기물 등 소각 금지

[산불 발생 시 대처법]
1. 산불 발견 즉시 119 또는 산림청 신고
2. 산불 발생 시 바람을 등지고 산불의 진행 반대 방향으로 대피
3. 산불은 빠른 속도로 확산되므로 신속히 대피
4. 대피 장소는 타버린 지역, 도로, 바위 뒤, 물가 등
5. 연기를 마시지 않도록 젖은 수건 등으로 코와 입을 보호
6. 불길에 휩싸일 경우 바람 부는 방향의 직각으로 대피

[산불 발생 시 신고]
- 산림청 신고: 042-481-4119
- 소방서 신고: 119

[산불 위험 등급]
- 위험 경보(적색): 산불 발생 위험이 매우 높음
- 주의 경보(황색): 산불 발생 위험이 높음
- 관심 경보(청색): 산불 발생 위험이 다소 높음
- 평상 경보(녹색): 산불 발생 위험이 낮음

[기타 산불 관련 정보]
- 산불 발생 예보: 기상청 및 산림청 홈페이지에서 확인 가능
- 산불 위험지수: 기온, 습도, 풍속, 강수량 등을 고려하여 산정
- 산불 조심 기간: 봄철(2월 1일 ~ 5월 15일), 가을철(11월 1일 ~ 12월 15일)
"""

@mcp.prompt()
def forest_fire_map_prompt(province: str = "", year: str = "") -> str:
    """특정 지역 및 연도의 산불 발생 위치를 지도에 표시하는 프롬프트를 생성합니다"""
    if province and year:
        return f"{year}년 {province} 지역의 산불 발생 위치를 지도에 표시해주세요."
    elif province:
        return f"{province} 지역의 산불 발생 위치를 지도에 표시해주세요."
    elif year:
        return f"{year}년에 발생한 산불 위치를 지도에 표시해주세요."
    else:
        return "산불 발생 위치를 지도에 표시해주세요."

@mcp.prompt()
def forest_fire_info_prompt(province: str = "", year: str = "") -> str:
    """특정 지역 및 연도의 산불 정보를 확인하는 프롬프트를 생성합니다"""
    if province and year:
        return f"{year}년 {province} 지역의 산불 발생 정보를 알려주세요."
    elif province:
        return f"{province} 지역의 산불 발생 정보를 알려주세요."
    elif year:
        return f"{year}년에 발생한 산불 정보를 알려주세요."
    else:
        return "산불 발생 정보를 알려주세요."

@mcp.prompt()
def forest_fire_stats_prompt() -> str:
    """산불 발생 통계 정보를 확인하는 프롬프트를 생성합니다"""
    return "산불 발생 통계 정보를 알려주세요."

@mcp.prompt()
def forest_fire_risk_prompt(province: str = "") -> str:
    """특정 지역의 산불 위험도를 분석하는 프롬프트를 생성합니다"""
    if province:
        return f"{province} 지역의 산불 위험도를 분석해주세요."
    else:
        return "산불 위험도를 분석해주세요."

@mcp.prompt()
def forest_fire_safety_prompt() -> str:
    """산불 예방 및 대처 요령을 확인하는 프롬프트를 생성합니다"""
    return "산불 예방 및 대처 요령을 알려주세요."

@mcp.tool()
async def visualize_fire_locations(region: str) -> str:
    """특정 지역의 산불 발생 위치를 지도에 표시합니다.
    
    Args:
        region: 표시할 지역명 (예: 강원도, 고성, 경상북도 등)
    
    Returns:
        지도 파일 경로 또는 결과 메시지
    """
    # 데이터 로드
    data = load_forest_fire_data()
    if isinstance(data, dict) and "error" in data:
        return data["error"]
    
    # 지역 필터링
    filtered_data = [item for item in data if region in item.get("location", "")]
    
    if not filtered_data:
        return f"{region} 지역에서 산불 발생 데이터를 찾을 수 없습니다."
    
    # 지역 중심점 검색
    region_lng, region_lat = await search_location_by_name(region)
    print(f"지역 중심점: {region_lng}, {region_lat}")
    
    # 마커 데이터 동적 생성
    marker_infos = []
    
    # 주소 검색 및 좌표 변환 시도
    for i, item in enumerate(filtered_data[:30]):  # 최대 30개만 처리 (API 호출 제한)
        location = item.get("location", "")
        if not location:
            continue
            
        # 주소로 좌표 찾기 시도
        try:
            # 카카오 로컬 API를 사용하여 주소 검색
            url = f"https://dapi.kakao.com/v2/local/search/address.json"
            headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
            params = {"query": location}
            
            response = requests.get(url, headers=headers, params=params)
            search_data = response.json()
            
            # 검색 결과가 있는 경우
            if "documents" in search_data and search_data["documents"]:
                lng = float(search_data["documents"][0]["x"])  # 경도
                lat = float(search_data["documents"][0]["y"])  # 위도
                print(f"주소 검색 성공 [{i+1}/{len(filtered_data)}]: {location} -> ({lng}, {lat})")
            else:
                # 좌표 정보 사용 (있는 경우)
                if "coordinates" in item and len(item["coordinates"]) == 2:
                    tm_x, tm_y = item["coordinates"]
                    # 간단한 TM 변환 사용
                    lng = tm_x * 0.000008 + 126.8
                    lat = tm_y * 0.000008 + 35.5
                    print(f"주소 검색 실패, 좌표 변환 시도 [{i+1}/{len(filtered_data)}]: {location} -> ({lng}, {lat})")
                else:
                    # 좌표 정보도 없는 경우 강원도 중심 좌표 사용
                    lng, lat = 128.45, 38.10  # 강원도 중부 좌표
                    print(f"주소 및 좌표 모두 실패 [{i+1}/{len(filtered_data)}]: {location}")
                    continue
            
            # 날짜 형식 포맷팅
            fire_date = item.get("fire_date", "날짜 정보 없음")
            if len(fire_date) == 12 and fire_date.isdigit():
                formatted_date = f"{fire_date[:4]}-{fire_date[4:6]}-{fire_date[6:8]} {fire_date[8:10]}:{fire_date[10:12]}"
            else:
                formatted_date = fire_date
            
            # 마커 정보 추가 (문자열 이스케이프 처리)
            location_esc = location.replace("'", "\\'").replace('"', '\\"')
            formatted_date_esc = formatted_date.replace("'", "\\'").replace('"', '\\"')
            fire_size = item.get("fire_size", "규모 정보 없음").replace("'", "\\'").replace('"', '\\"')
            fire_cause = item.get("fire_cause", "원인 정보 없음").replace("'", "\\'").replace('"', '\\"')
            
            marker_info = {
                "lat": lat,
                "lng": lng,
                "title": location_esc,
                "date": formatted_date_esc,
                "size": fire_size,
                "cause": fire_cause
            }
            marker_infos.append(marker_info)
            
            # API 호출 제한을 위한 딜레이
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"오류 발생 [{i+1}/{len(filtered_data)}]: {location} - {str(e)}")
    
    # 마커가 없으면 기본 좌표로 설정 (강원도 중심)
    if not marker_infos:
        return f"{region} 지역의 산불 위치를 지도에 표시할 수 없습니다. 주소 검색에 실패했습니다."
    
    # 중심점 계산 (모든 마커의 평균)
    avg_lng = sum(item["lng"] for item in marker_infos) / len(marker_infos)
    avg_lat = sum(item["lat"] for item in marker_infos) / len(marker_infos)
    
    # 중심점 설정 (우선순위: 검색 결과 > 마커 평균 > 고정 좌표)
    center_lng = region_lng if region_lng else (avg_lng if marker_infos else 128.45)
    center_lat = region_lat if region_lat else (avg_lat if marker_infos else 38.10)
    
    # JSON 데이터를 안전하게 직렬화
    marker_json = json.dumps(marker_infos, ensure_ascii=False)
    
    # 지도 HTML 생성
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{region} 산불 발생 지도</title>
        <style>
            body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; }}
            #map {{ width: 100%; height: 100%; }}
            .info-window {{ padding: 10px; max-width: 300px; font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Nanum Gothic', 'Dotum', sans-serif; }}
            .info-window h4 {{ margin-top: 0; margin-bottom: 10px; font-size: 14px; font-weight: bold; color: #333; }}
            .info-window p {{ margin: 5px 0; font-size: 13px; color: #666; }}
            .info-window .label {{ font-weight: bold; color: #444; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_MAP_API_KEY}"></script>
        <script>
            // 지도 생성
            var container = document.getElementById('map');
            var options = {{
                center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                level: 9,
                mapTypeId: kakao.maps.MapTypeId.ROADMAP
            }};
            
            var map = new kakao.maps.Map(container, options);
            
            // 지도 타입 컨트롤
            var mapTypeControl = new kakao.maps.MapTypeControl();
            map.addControl(mapTypeControl, kakao.maps.ControlPosition.TOPRIGHT);
            
            // 줌 컨트롤
            var zoomControl = new kakao.maps.ZoomControl();
            map.addControl(zoomControl, kakao.maps.ControlPosition.RIGHT);
            
            // 마커 이미지 생성
            var markerImageSrc = 'https://t1.daumcdn.net/localimg/localimages/07/mapapidoc/markerStar.png';
            var markerImageSize = new kakao.maps.Size(24, 35);
            var markerImage = new kakao.maps.MarkerImage(markerImageSrc, markerImageSize);
            
            // 마커 배열
            var markers = [];
            
            // 마커 데이터
            var markerData = {marker_json};
            
            console.log("총 마커 데이터:", markerData.length, "개");
            
            // 마커 생성 및 추가
            for (var i = 0; i < markerData.length; i++) {{
                var data = markerData[i];
                
                // 유효한 좌표 확인 (대한민국 영역 내)
                if (data.lng < 124 || data.lng > 132 || data.lat < 33 || data.lat > 43) {{
                    console.log("범위 외 좌표 무시:", data.title, data.lat, data.lng);
                    continue;
                }}
                
                var marker = new kakao.maps.Marker({{
                    position: new kakao.maps.LatLng(data.lat, data.lng),
                    title: data.title,
                    image: markerImage
                }});
                
                // 정보창 내용
                var iwContent = '<div class="info-window">' +
                    '<h4>' + data.title + '</h4>' +
                    '<p><span class="label">발생일자:</span> ' + data.date + '</p>' +
                    '<p><span class="label">규모:</span> ' + data.size + '</p>' +
                    '<p><span class="label">원인:</span> ' + data.cause + '</p>' +
                    '</div>';
                    
                // 인포윈도우 생성
                var infowindow = new kakao.maps.InfoWindow({{
                    content: iwContent,
                    removable: true
                }});
                
                // 클릭 이벤트 등록
                (function(marker, infowindow) {{
                    kakao.maps.event.addListener(marker, 'click', function() {{
                        infowindow.open(map, marker);
                    }});
                }})(marker, infowindow);
                
                marker.setMap(map);
                markers.push(marker);
            }}
            
            // 모든 마커를 포함하는 영역으로 지도 범위 재설정
            if (markers.length > 0) {{
                var bounds = new kakao.maps.LatLngBounds();
                for (var i = 0; i < markers.length; i++) {{
                    bounds.extend(markers[i].getPosition());
                }}
                map.setBounds(bounds);
                
                // 데이터가 너무 많을 경우 적절한 줌 레벨 설정
                if (markers.length > 100) {{
                    map.setLevel(Math.min(10, map.getLevel() + 1));
                }}
            }} else {{
                // 마커가 없는 경우 중심점 기준으로 지도 표시
                console.log("표시할 마커가 없습니다. 중심점 기준으로 지도를 표시합니다.");
            }}
            
            console.log("총", markers.length, "개의 산불 발생 위치를 지도에 표시했습니다.");
        </script>
    </body>
    </html>
    """
    
    # 임시 HTML 파일 생성 및 열기
    with tempfile.NamedTemporaryFile(delete=False, suffix='.html', mode='w', encoding='utf-8') as f:
        f.write(html_content)
        temp_file_path = f.name
    
    # 웹 브라우저로 파일 열기
    webbrowser.open('file://' + temp_file_path)
    
    return f"""
{region} 지역의 산불 발생 지점 {len(filtered_data)}개 중 {len(marker_infos)}개의 위치를 지도에 표시했습니다.
웹 브라우저가 열리지 않으면, 다음 파일을 수동으로 열어주세요: {temp_file_path}
"""

@mcp.tool()
async def set_kakao_map_api_key(api_key: str) -> str:
    """카카오맵 API 키를 설정합니다.
    
    Args:
        api_key: 카카오맵 JavaScript API 키
        
    Returns:
        설정 결과 메시지
    """
    global KAKAO_MAP_API_KEY
    KAKAO_MAP_API_KEY = api_key
    return f"카카오맵 API 키가 성공적으로 설정되었습니다. 이제 지도 시각화 기능을 사용할 수 있습니다."

def convert_tm_to_wgs84(tm_x: float, tm_y: float) -> Tuple[float, float]:
    """TM 좌표를 WGS84 좌표로 변환합니다 (카카오 로컬 API 사용).
    
    Args:
        tm_x: TM 좌표계의 X 좌표
        tm_y: TM 좌표계의 Y 좌표
        
    Returns:
        (경도, 위도) 튜플 (WGS84)
    """
    try:
        # 좌표계 변환 시도
        url = "https://dapi.kakao.com/v2/local/geo/transcoord.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
        params = {
            "x": tm_x,
            "y": tm_y,
            "input_coord": "TM",
            "output_coord": "WGS84"
        }
        
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        # 디버깅용 출력
        print(f"[API 응답] {response.status_code}: {str(data)[:200]}...")
        
        if "documents" in data and data["documents"]:
            x = float(data["documents"][0]["x"])  # 경도
            y = float(data["documents"][0]["y"])  # 위도
            
            # 좌표 범위 검증 (대한민국 영역: 대략 125~132, 33~43)
            if 125 <= x <= 132 and 33 <= y <= 43:
                return (x, y)
    except Exception as e:
        print(f"좌표 변환 오류: {e}")
    
    # 변환 실패 시 예상 좌표 계산 (간단한 근사 변환)
    # 이는 매우 대략적인 변환이므로 정확하지 않음
    try:
        # 국내 TM 좌표를 WGS84로 대략적 변환 (선형 근사)
        # 이 값들은 대략적인 스케일 및 오프셋 값으로, 정확한 변환이 아님
        lng = tm_x * 0.000009 + 126.0
        lat = tm_y * 0.000009 + 32.0
        print(f"대략적 좌표 변환 사용: ({tm_x}, {tm_y}) -> ({lng:.6f}, {lat:.6f})")
        return (lng, lat)
    except Exception as e:
        print(f"좌표 근사 변환 오류: {e}")
    
    # 모든 변환 실패 시 임의의 유효 좌표 반환 (강원도 고성 부근)
    print(f"좌표 변환 최종 실패: ({tm_x}, {tm_y}) -> 기본값 사용")
    return (128.4677, 38.3806)

if __name__ == "__main__":
    print("산불정보 시각화 MCP 서버를 시작합니다...")
    print(f"데이터 파일 경로: {FOREST_FIRE_DATA_PATH}")
    print("카카오맵 API 키가 설정되어 있는지 확인하세요.")
    print("서버가 시작되면 AI 에이전트에서 산불 정보를 질문해보세요!")
    mcp.run() 