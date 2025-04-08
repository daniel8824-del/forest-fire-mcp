import geopandas as gpd
import json
import os

# 입력 Shapefile 경로와 출력 JSON 파일 경로 설정
INPUT_SHAPEFILE = "TB_FFAS_FF_OCCRR_42.shp"
OUTPUT_JSON = "forest_fire_data.json"

def convert_shapefile_to_json():
    """
    Shapefile을 JSON으로 변환합니다.
    """
    try:
        print(f"Shapefile 데이터 읽는 중: {INPUT_SHAPEFILE}")
        
        # Shapefile 읽기
        gdf = gpd.read_file(INPUT_SHAPEFILE, encoding='euc-kr')
        
        # 데이터 정보 출력
        print(f"데이터 형태: {gdf.shape}")
        print("데이터 열 목록:")
        for col in gdf.columns:
            print(f"  - {col}")
        
        # 지오메트리를 좌표로 변환
        gdf['coordinates'] = gdf.geometry.apply(lambda geom: 
                                               [round(geom.x, 5), round(geom.y, 5)] 
                                               if geom else [])
        
        # JSON으로 변환할 데이터 준비
        records = []
        for _, row in gdf.iterrows():
            # 실제 데이터 열 기반으로 매핑 
            record = {
                "location": "",
                "fire_date": "",
                "fire_size": "",
                "fire_cause": "",
                "coordinates": row['coordinates']
            }
            
            # 위치 정보
            if 'CTPRV_NM' in row and 'SGNG_NM' in row:
                location_parts = []
                if row['CTPRV_NM'] and str(row['CTPRV_NM']) != 'nan':
                    location_parts.append(str(row['CTPRV_NM']))
                if row['SGNG_NM'] and str(row['SGNG_NM']) != 'nan':
                    location_parts.append(str(row['SGNG_NM']))
                if 'EMNDN_NM' in row and row['EMNDN_NM'] and str(row['EMNDN_NM']) != 'nan':
                    location_parts.append(str(row['EMNDN_NM']))
                if 'OCCCRR_RI' in row and row['OCCCRR_RI'] and str(row['OCCCRR_RI']) != 'nan':
                    location_parts.append(str(row['OCCCRR_RI']))
                
                record['location'] = " ".join(location_parts)
            
            # 발생 일시    
            if 'OCCRR_DTM' in row and row['OCCRR_DTM'] and str(row['OCCRR_DTM']) != 'nan':
                record['fire_date'] = str(row['OCCRR_DTM'])
            
            # 피해 면적
            if 'DMG_AREA' in row and row['DMG_AREA'] and str(row['DMG_AREA']) != 'nan':
                record['fire_size'] = str(row['DMG_AREA']) + "ha"
            
            # 원인
            if 'CUSE_NM' in row and row['CUSE_NM'] and str(row['CUSE_NM']) != 'nan':
                record['fire_cause'] = str(row['CUSE_NM'])
            
            records.append(record)
        
        # JSON 파일 저장
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        
        print(f"데이터 변환 완료: {len(records)}개 산불 데이터 추출")
        print(f"JSON 파일 저장 위치: {OUTPUT_JSON}")
        
        return True
        
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        
        # geopandas가 설치되어 있지 않은 경우
        if "No module named 'geopandas'" in str(e):
            print("\ngeopandas가 설치되어 있지 않습니다. 다음 명령으로 설치하세요:")
            print("pip install geopandas")
            print("만약 설치 중 오류가 발생한다면, 다음 패키지들을 먼저 설치해보세요:")
            print("pip install numpy pandas pyproj fiona shapely")
        
        return False

if __name__ == "__main__":
    convert_shapefile_to_json() 