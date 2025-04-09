import blenderproc as bproc
import os
import numpy as np
import argparse
import glob
import random
import bpy

parser = argparse.ArgumentParser()
parser.add_argument('scene_net_obj_path', default="SceneNetData/1Bedroom/bedroom_1.obj", help="Path to the used scene net `.obj` file, download via scripts/download_scenenet.py")
parser.add_argument('scene_texture_path', default="./",help="Path to the downloaded texture files, you can find them at http://tinyurl.com/zpc9ppb")
# parser.add_argument('output_dir', nargs='?', default="output/", help="Path to where the final files, will be saved")
parser.add_argument('hdri_path', nargs='?', default="world", help="The folder where the `hdri` folder can be found, to load an world environment")
args = parser.parse_args()

bproc.init() 

# Set random texture backround to global shader
#haven_hdri_path = bproc.loader.get_random_world_background_hdr_img_path_from_haven(args.hdri_path)  
hdr_files = glob.glob(os.path.join(os.path.join(args.hdri_path, "hdris"),"*.exr")) 
print(len(hdr_files))
hdr_files.sort() 
random_hdr_file = random.choice(hdr_files)
bproc.world.set_world_background_hdr_img(random_hdr_file) 

# Load the scenenet room and label its objects with category ids based on the nyu mapping
label_mapping = bproc.utility.LabelIdMapping.from_csv(bproc.utility.resolve_resource(os.path.join('id_mappings', 'nyu_idset.csv')))
#scene_objs = bproc.loader.load_scenenet("SceneNetData/1Bedroom/bedroom_1.obj", args.scene_texture_path, label_mapping)
scene_objs = bproc.loader.load_scenenet(args.scene_net_obj_path, args.scene_texture_path, label_mapping)

# In some scenes floors, walls and ceilings are one object that needs to be split first
# Collect all walls
walls = bproc.filter.by_cp(scene_objs, "category_id", label_mapping.id_from_label("wall"))
# Extract floors from the objects
new_floors = bproc.object.extract_floor(walls, new_name_for_object="floor", should_skip_if_object_is_already_there=True)
# Set category id of all new floors
for floor in new_floors:
    floor.set_cp("category_id", label_mapping.id_from_label("floor"))
# Add new floors to our total set of objects
scene_objs += new_floors

# Extract ceilings from the objects
new_ceilings = bproc.object.extract_floor(walls, new_name_for_object="ceiling", up_vector_upwards=False, should_skip_if_object_is_already_there=True)
# Set category id of all new ceiling
for ceiling in new_ceilings:
    ceiling.set_cp("category_id", label_mapping.id_from_label("ceiling"))
# Add new ceilings to our total set of objects
scene_objs += new_ceilings

for obj in scene_objs:
    if  isinstance(obj, bproc.types.MeshObject):
        location = obj.get_location()
        location[2] -= 1
        obj.set_location(location)
        ori_scale = obj.get_scale()
        obj.set_scale(ori_scale * 80)

# Merge scene objects to one object => Can be removed, added for UI simplication
bproc.object.merge_objects(scene_objs, merged_object_name='merged_scene_objects') 

# Make all lamp objects emit light
lamps = bproc.filter.by_attr(scene_objs, "name", ".*[l|L]amp.*", regex=True)
bproc.lighting.light_surface(lamps, emission_strength=15)
# Also let all ceiling objects emit a bit of light, so the whole room gets more bright
ceilings = bproc.filter.by_attr(scene_objs, "name", ".*[c|C]eiling.*", regex=True)
bproc.lighting.light_surface(ceilings, emission_strength=2, emission_color=[1,1,1,1])
 
#########################################################################################################
# load head models(only mesh objects): 
#Tongue, Teeth, Realtime Eyeball Right, Realtime Eyeball Left, Lens Right, Lens Left, Lashes, Head, Eye Wet, Brows
head_objs = bproc.loader.load_blend('model.blend', data_blocks=["objects"], obj_types=["mesh"]) 
  
# Set head as parent
#ver1: set 'Head' as parent
head_master = bproc.filter.one_by_attr(head_objs, "name", "Head")
for obj in head_objs:
    obj.set_origin(mode= "CENTER_OF_MASS")
    if obj.get_name() != "Head":
          obj.set_parent(head_master)   

# ver2: create new object and set it as parent to all head related objects
#bproc.object.merge_objects(head_objs, merged_object_name='merged_head_objects')
 
#########################################################################################################
# Settings for eye reflection
# 1. Add Emission Shader to scene objects
# 2. Change the "Lens" object's material to Glossy(Mirror effect)-GT
# 3. TODO: reflection on real eyes mat(Realtime Eyeball) unsolved

# Add emission shader    
emissive_objs = []
for obj in scene_objs:
    if obj not in lamps and ceilings:
        emissive_objs.append(obj)
emissive_objs.append(head_master)
bproc.lighting.light_surface(emissive_objs, emission_strength=1)

# Create mirror-like material for Eye Lens
eye_lens = bproc.filter.by_attr(head_objs, "name", "Lens Left", regex=True)
#eye_lens = bproc.filter.by_attr(head_objs, "name", "^Lens.*", regex=True)


for lens in eye_lens:
    print(lens.get_name())
    if not lens.has_materials():
        print("added new material")
        empty_material = lens.new_material("TextureLess")
        lens.add_material(empty_material) 

    for i, material in enumerate(lens.get_materials()):
        if material is None:
            continue
        # if there is more than one user make a copy and then use the new one
        if material.get_users() > 1:
            material = material.duplicate()
            lens.set_material(i, material)
        # rename the material
        material.set_name(lens.get_name() + "_glossy") 
        # get output node
        output_node = material.get_the_one_node_with_type("OutputMaterial")
        output_socket = output_node.inputs['Surface'] 
        # create glossy shader and link to output
        glossy_node = material.new_node('ShaderNodeBsdfGlossy')
        glossy_node.inputs['Roughness'].default_value = 0 # Roughness=0.0, Metalic=1.0 for mirror-like material
        material.link(glossy_node.outputs["BSDF"], output_socket)

    # move the lens object a bit forward to minimize the reflection of the face
    loc = lens.get_location()
    loc[1] -= 0.2
    lens.set_location(loc)
     
scene_objs += head_objs
#########################################################################################################
# sample head locations
#head_loc = bpy.data.objects["Head"].location 
head_loc = head_master.get_location()
head_loc[0] += 100
head_loc[2] += 30
head_master.set_location(head_loc)
# Find head object's location
#head_location = bproc.filter.by_attr(bproc.filter.all_with_type(objs, bproc.types.MeshObject), "name", "Head", regex=True)[0].get_location() 
print("???")
# Find point of interest, all cam poses should look towards it
poi_head = bproc.object.compute_poi(head_objs)
temp2 = bproc.object.create_empty("POI head")
temp2.set_location(poi_head)
#########################################################################################################
# Find eye location 
eye_left = bproc.filter.one_by_attr(head_objs, "name", "Realtime Eyeball Left")
lens_left = bproc.filter.one_by_attr(head_objs, "name", "Lens Left")
#eye_loc =  eye_left.get_location()
#location = eye_loc  
eye_left.set_origin(mode= "CENTER_OF_MASS")
eye_origin = eye_left.get_location()
temp6 = bproc.object.create_empty("origin_left_eye")
temp6.set_location(eye_origin) 

poi_eyes = bproc.object.compute_poi([lens_left, eye_left])
poi_eyes[1] -= 2 # y axis
temp5 = bproc.object.create_empty("POI left_eye")
temp5.set_location(poi_eyes) 

# set camera location
location = poi_eyes
 
poses = 0
tries = 0
cam_dist = 0
# Sample five camera poses
while tries < 10000 and poses < 1: 
    tries += 1 
    # Samples a point from the surface of solid sphere 
    #location = bproc.sampler.part_sphere(center=poi_head, radius=12, part_sphere_dir_vector=[0, -1, 0], mode="SURFACE", dist_above_center=8.0)
    
    # move camera further backwards
    location[1] -= 3 # y axis
   
    ## raycasting 
    # _, _, _, _, hit_object, _ = bproc.object.scene_ray_cast(origin=location, direction=[0, 1, 0])
    # if hit_object not in head_objs:
    #     # returns 8x3 array describing the object aligned bounding box coordinates in world coordinates
    #     #hit_object.get_bound_box()  
    #     continue
    # print(hit_object.get_name())
    
    # Compute rotation based on vector going from location towards poi
    rotation_matrix = bproc.camera.rotation_from_forward_vec(poi_eyes - location) #, up_axis = 'Z') #,inplane_rot=90) 
    temp4 = bproc.object.create_empty("camera loc_"+str(poses))
    temp4.set_location(location) 
    
    # Add homog cam pose based on location an rotation
    cam2world_matrix = bproc.math.build_transformation_mat(location, rotation_matrix)  
    # OpenCV -> OpenGL (fixing camera coord)
    cam2world_matrix = bproc.math.change_source_coordinate_frame_of_transformation_matrix(cam2world_matrix, ["X", "Z", "-Y"])
    
    # Sample input image with eye lens(mirror tex)
    lens_left.hide(False)
    print("lens should not be hidden(False): "+str(lens_left.is_hidden()))
    bproc.camera.add_camera_pose(cam2world_matrix)

    # # Sample input image with deactivating eye lens(mirror tex) 
    # lens_left.hide(True) # lens hiding works
    # print("lens should be hidden(True): "+str(lens_left.is_hidden()))
    # bproc.camera.add_camera_pose(cam2world_matrix)
    
    poses += 1

# activate normal and depth rendering
#bproc.renderer.enable_normals_output()
#bproc.renderer.enable_depth_output(activate_antialiasing=False)

# render the whole pipeline
data = bproc.renderer.render()

# write the data to a .hdf5 container
bproc.writer.write_hdf5("output_scene/", data)


'''while tries < 10000 and poses < 5:
    tries += 1
    # Sample point above the floor in height of [1.5m, 1.8m]
    location = bproc.sampler.upper_region(floors, min_height=1.5, max_height=1.8)
    # Check that there is no object between the sampled point and the floor
    _, _, _, _, hit_object, _ = bproc.object.scene_ray_cast(location, [0, 0, -1])
    if hit_object not in floors:
        continue

    # Sample rotation (fix around X and Y axis)
    rotation = np.random.uniform([1.2217, 0, 0], [1.2217, 0, 2 * np.pi])
    cam2world_matrix = bproc.math.build_transformation_mat(location, rotation)

    # Check that there is no obstacle in front of the camera closer than 1m
    if not bproc.camera.perform_obstacle_in_view_check(cam2world_matrix, {"min": 1.0}, bvh_tree):
        continue

    # Check that the interesting score is not too low
    if bproc.camera.scene_coverage_score(cam2world_matrix) < 0.1:
        continue

    # If all checks were passed, add the camera pose
    bproc.camera.add_camera_pose(cam2world_matrix)
    poses += 1

# activate normal and depth rendering
bproc.renderer.enable_normals_output()
bproc.renderer.enable_depth_output(activate_antialiasing=False)
bproc.renderer.enable_segmentation_output(map_by=["category_id"])

# render the whole pipeline
data = bproc.renderer.render()

# write the data to a .hdf5 container
bproc.writer.write_hdf5(args.output_dir, data)'''
