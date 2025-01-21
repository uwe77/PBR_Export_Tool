import bpy

def Export(self, context, export_path, texture_resolution, device, material, export_items):
    # Acquire language settings
    lang = bpy.app.translations.locale

    # Deselect all objects
    bpy.ops.object.select_all(action='DESELECT')

    # Delete temp collection if it exists
    for collection in bpy.data.collections:
        if collection.name == 'PBR_Export_Temp':
            for obj in collection.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(collection)

    # Delete temp plane if it exists
    for obj in bpy.data.objects:
        if obj.name == 'Temp_Plane':
            bpy.data.objects.remove(obj, do_unlink=True)

    # Create initial plane
    temp_collection = bpy.data.collections.new('PBR_Export_Temp')
    bpy.context.scene.collection.children.link(temp_collection)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children['PBR_Export_Temp']
    bpy.ops.mesh.primitive_plane_add()
    bpy.context.active_object.name = 'Temp_Plane'

    # Save previous rendering settings
    previous_settings = {
        "render_engine": bpy.context.scene.render.engine,
        "device": bpy.context.scene.cycles.device,
        "use_adaptive_sampling": bpy.context.scene.cycles.use_adaptive_sampling,
        "samples": bpy.context.scene.cycles.samples,
        "min_samples": bpy.context.scene.cycles.adaptive_min_samples,
        "use_denoising": bpy.context.scene.cycles.use_denoising,
        "time_limit": bpy.context.scene.cycles.time_limit,
        "display_device": bpy.context.scene.display_settings.display_device,
        "view_transform": bpy.context.scene.view_settings.view_transform,
        "look": bpy.context.scene.view_settings.look,
        "exposure": bpy.context.scene.view_settings.exposure,
        "gamma": bpy.context.scene.view_settings.gamma,
        "sequencer_colorspace": bpy.context.scene.sequencer_colorspace_settings.name,
        "use_curve_mapping": bpy.context.scene.view_settings.use_curve_mapping,
    }

    # Change rendering settings
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = device
    bpy.context.scene.cycles.use_adaptive_sampling = False
    bpy.context.scene.cycles.samples = 1
    bpy.context.scene.cycles.adaptive_min_samples = 1
    bpy.context.scene.cycles.use_denoising = False
    bpy.context.scene.cycles.time_limit = 0
    bpy.context.scene.display_settings.display_device = 'sRGB'
    bpy.context.scene.view_settings.view_transform = 'Standard'
    bpy.context.scene.view_settings.look = 'None'
    bpy.context.scene.view_settings.exposure = 0
    bpy.context.scene.view_settings.gamma = 1
    bpy.context.scene.sequencer_colorspace_settings.name = 'sRGB'
    bpy.context.scene.view_settings.use_curve_mapping = False

    # Assign material
    mat = material
    bpy.context.active_object.data.materials.append(mat)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes

    # Check and clean up nodes
    for node in nodes:
        if node.name == 'PBR_Bake_Node':
            nodes.remove(node)
    
    material_output_node = None
    for node in nodes:
        if node.type == 'OUTPUT_MATERIAL':
            if material_output_node is not None:
                self.report({'ERROR'}, "Multiple material output nodes found!")
                return {'CANCELLED'}
            material_output_node = node

    if not material_output_node:
        self.report({'ERROR'}, "No material output node found!")
        return {'CANCELLED'}

    material_output_socket = material_output_node.inputs['Surface']
    if len(material_output_socket.links) == 0:
        self.report({'ERROR'}, "No shader connected to material output node!")
        return {'CANCELLED'}

    shader_node = material_output_socket.links[0].from_node
    if shader_node.type != "BSDF_PRINCIPLED":
        self.report({'ERROR'}, "Only Principle BSDF shader is supported!")
        return {'CANCELLED'}

    # Process export items (BaseColor, Metallic, Roughness, Normal)
    def bake_texture(texture_type, socket_name, colorspace, file_suffix):
        texture_node = nodes.new('ShaderNodeTexImage')
        texture_node.name = 'PBR_Bake_Node'
        texture_node.select = True
        nodes.active = texture_node
        img = bpy.data.images.new(f"{material.name}_{texture_resolution}x{texture_resolution}_{file_suffix}",
                                  texture_resolution, texture_resolution)
        texture_node.image = img

        for img in bpy.data.images:
            if img.colorspace_settings.name != '':
                img.colorspace_settings.name = colorspace

        socket = shader_node.inputs[socket_name]
        if len(socket.links) == 0:
            socket_value = socket.default_value
            shader_node.inputs['Emission'].default_value = [socket_value] * 3 + [1.0]
        else:
            mat.node_tree.links.new(socket.links[0].from_socket, shader_node.inputs['Emission'])

        bpy.ops.object.bake(type='EMIT', save_mode='EXTERNAL', width=texture_resolution, height=texture_resolution)
        img.save_render(filepath=f"{export_path}{material.name}/{material.name}_{texture_resolution}x{texture_resolution}_{file_suffix}.png")

        nodes.remove(texture_node)

    if export_items[0]:  # BaseColor
        bake_texture('Base Color', 'Base Color', 'sRGB', 'BaseColor')
    if export_items[1]:  # Metallic
        bake_texture('Metallic', 'Metallic', 'sRGB', 'Metallic')
    if export_items[2]:  # Roughness
        bake_texture('Roughness', 'Roughness', 'sRGB', 'Roughness')
    if export_items[3]:  # Normal
        bake_texture('Normal', 'Normal', 'Non-Color', 'Normal')

    # Restore rendering settings
    for key, value in previous_settings.items():
        setattr(bpy.context.scene.cycles, key, value)

    # Delete temporary plane
    bpy.ops.object.delete()
    bpy.data.collections.remove(temp_collection)
