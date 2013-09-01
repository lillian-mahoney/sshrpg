import random
import math
from config import ini
import sqlcanvas
import database
import brush


# CONSTANTS/CONFIG ############################################################


TILE_TYPES = ini('tiles')
TILE_TYPES[None] = TILE_TYPES['default']


# TERRAIN #####################################################################


def generate_lake(canvas, scene, seed=None, max_blobs=0, radius=None, lake_i=0):
    lakes = scene['lakes']
    max_radius = int(lakes['max_radius'])  # blob size
    min_radius = int(lakes['min_radius'])  # blob size
    min_corner_radius = int(lakes['min_corner_radius'])  # percent
    max_corner_radius = int(lakes['max_corner_radius'])  # percent
    corner_radius = random.randint(min_corner_radius, max_corner_radius)

    if radius is None:
       radius = random.randint(min_radius, max_radius)

    corner_radius = int(radius * float('0.' + str(corner_radius)))
    threshold = int(lakes.get('shore_threshold', 125))
    coords = canvas.cache['coords']
    area = canvas.cache['area']

    # place the seed, grow the lake
    seed = list(coords)[random.randint(0, area - 1)]
    lake = brush.expand((seed,), radius, coords)
    parameter = brush.parameter(lake)

    # perlin noise!
    step_thresh = threshold / radius
    remove = []

    for coord in coords:
        score = random.randint(0, 250)
        dist = distance(coord, seed)
        distance_penalty = dist * (radius / (dist or 1))

        if score < threshold + distance_penalty:
            remove.append(coord)

    remove = set(remove)
    lake = lake.difference(remove)
    lake = lake.union(brush.expand((seed,), int(radius * 0.90), coords))
    remove = []

    # round corners
    penalty_math = int(250 / len(parameter)) or 1
    penalty = 0
    corners = brush.corners(lake)

    for corner in corners:
        corner = brush.expand((corner,), corner_radius, coords)

        for coord in corner:
            score = random.randint(0, 250)
            dist = distance(coord, seed)
            dist_penalty = dist * (radius / (dist or 1)) + penalty

            if score < threshold + distance_penalty:
                remove.append(coord)
                penalty += penalty_math

            penalty = 0

    remove = set(remove)
    lake = lake.difference(remove)
    possible_seeds = brush.expand((seed,), int(radius * 0.50), coords)
    lake = lake.union(possible_seeds)
    # remove random from parameter
    remove = []
    penalty = 0

    for coord in parameter:
        score = random.randint(0, 250)
        dist = distance(coord, seed)
        dist_penalty = dist * (radius / (dist or 1)) + penalty

        if score < threshold + distance_penalty:
            remove.append(coord)
            penalty += penalty_math

        penalty = 0

    if max_blobs:
        possible_seeds = list(possible_seeds)
        max_possible_seeds_index = len(possible_seeds) - 1

        while True:
            new_seed = possible_seeds[random.randint(0, max_possible_seeds_index)]
            dist = distance(new_seed, seed)

            if dist > math.sqrt(radius * 0.25) or dist > math.sqrt(radius * 0.15):
                continue
            else:
                break

        max_blobs -= 1
        #radius -= min([int(radius * 0.75), min_radius])
        lake_blob = generate_lake(
                                  canvas,
                                  scene,
                                  new_seed,
                                  max_blobs=max_blobs,
                                  radius=radius
                                 )

    remove = set(remove)
    lake = lake.difference(remove)
    canvas.subset('lake_%d' % lake_i, lake, tile_type='water')
    return seed


def generate_lakes(canvas, scene):
    lakes = scene['lakes'] 
    # for when I do more complicated formations of lakes
    min_lakes = int(lakes['minimum'])
    max_lakes = int(lakes['maximum'])
    max_blobs = int(lakes['max_blobs'])
    min_blobs = int(lakes['min_blobs'])
    blobs = random.randint(min_blobs, max_blobs)
    number_of_lakes = random.randint(min_lakes, max_lakes)

    for lake in xrange(number_of_lakes):
        generate_lake(canvas, scene, max_blobs=blobs, lake_i=lake)

    return number_of_lakes


# ROOMS #######################################################################


def viable(length_min, length_max, value_min, value_max):
    random_a = random.randint(value_min, value_max)
    random_b = random.randint(value_min, value_max)
    length = abs(random_a - random_b)

    if not value_max >= length >= value_min:
        return None, None

    if not length_max >= length >= length_min:
        return None, None

    if random_a < random_b:
        start = random_a
        end = random_b
    else:
        start = random_b
        end = random_a

    return start, end
 

def generate_house(room_name, canvas, scene):
    houses = scene['houses']

    # info we need...
    min_x, min_y = canvas.cache['top_left']
    max_x, max_y = canvas.cache['bottom_right']
    coords = canvas.cache['coords']
    parameter = canvas.cache['parameter']
    room_x_min = int(houses['x_min'])
    room_y_min = int(houses['y_min'])
    room_x_max = int(houses['x_max'])
    room_y_max = int(houses['y_max'])
    room_min_distance = int(houses['margin'])
    room_max_doors = int(houses['max_doors_per'])

    # determine top left and bottom right, basically
    start_x, end_x = viable(room_x_min, room_x_max, min_x, max_x)
    if start_x is None: return None, None
    start_y, end_y = viable(room_y_min, room_y_max, min_y, max_y)
    if start_y is None: return None, None
    start = (start_x, start_y)
    end = (end_x, end_y)

    # figure out area, boundary restrictions
    area = brush.rectangle(end, start)
    padded_area = brush.expand(area, room_min_distance, coords)

    # is any part of padded_area in another subset?
    if canvas.belongs(padded_area):
        return None, None

    for plot in padded_area:
        if TILE_TYPES[canvas[plot]['tile_type']]['impassable'] == 'true':
            return None, None

    room_name = 'room_%s' % room_name
    canvas.subset(room_name, area, tile_type='floor')
    walls = brush.parameter(area)
    canvas.update(walls, tile_type='wall')
    doors = room_place_doors(canvas, area, room_max_doors)
    return room_name, doors

 
def generate_houses(canvas, scene):
    houses = scene['houses']
    rooms_max = int(houses['build_max'])
    rooms_min = int(houses['build_min'])
    enable_paths = int(houses.get('paths', 0))

    # we're going to map a door per door witha path
    total_door_coords = {}

    # choose total number of rooms to generate
    houses_to_generate = random.randint(rooms_min, rooms_max)

    while houses_to_generate:
        room_name, doors = generate_house(houses_to_generate, canvas, scene)
        if room_name is None: continue
        total_door_coords[room_name] = doors
        houses_to_generate -= 1

    # path generation!
    if enable_paths:
        generate_paths(canvas, total_door_coords)

    return houses_to_generate


# generate scene
def generate_scene(canvas, scene, atop_water=False):
    scene = ini('scenes/' + scene)
    has_section = lambda x: scene.get(x, None)

    if has_section('decorations'):
        generate_decorations(canvas, scene)

    if has_section('rivers'):
        generate_rivers(canvas, scene)

    if has_section('lakes'):
        generate_lakes(canvas, scene)
 
    if has_section('houses'):
        generate_houses(canvas, scene)

    return None


def generate_rivers(canvas, scene):
    """A currently shitty river generator."""

    rivers = scene['rivers']
    rivers_min = int(rivers.get('min', 0))
    rivers_max = int(rivers.get('max', 0))

    river_min_length = int(rivers.get('min_length', 0))
    river_max_length = int(rivers.get('max_length', 0))

    parameter = list(canvas.cache['parameter'])
    rivers_to_gen = random.randint(rivers_min, rivers_max)
    possible_plots = len(parameter)
    start_point = parameter[random.randint(0, possible_plots - 1)]
    end_point = parameter[random.randint(0, possible_plots - 1)]

    find_point = lambda: parameter[random.randint(0, possible_plots - 1)]
    rivers_generated = 0

    while True:
        # don't escape until a long enough river has been generated!

        # do we have enough rivers?
        if rivers_generated == rivers_to_gen:
            break

        start_point = find_point()
        end_point = find_point()
        river_length = distance(start_point, end_point)

        # check if river is long/short enough
        if river_length < river_min_length or river_length > river_max_length:
            continue

        river = astar(canvas, start_point, end_point)
        canvas.subset('river_%d' % rivers_generated, river, tile_type='water')
        rivers_generated += 1

    return rivers_generated


def generate_decorations(canvas, scene):
    decorations = scene['decorations']
    tiles = decorations['tiles'].split(',')

    max_decor_i = len(tiles) - 1
    percent_min = int(decorations['percent_min'])
    percent_max = int(decorations['percent_max'])
    percent = str(random.randint(percent_min, percent_max))

    if len(percent) < 3:
        percent = float('0.' + percent)
    else:
        percent = float('1.0')

    area = canvas.cache['area']
    coords = canvas.cache['coords']
    available = int(float(area) * percent) + 1

    try:
        __, selected = brush.omit_random(coords, available)
    except:
        raise Exception(available)

    for coord in selected:
        selected_decor = tiles[random.randint(0, max_decor_i)]
        canvas.update([coord], tile_type=selected_decor)

    return percent


def generate_paths(canvas, total_door_coords):
    """Generate paths from one door to another via A*

    total_door_coords should be sql select * from coord_defs where
    tile_type="door"

    """

    doors_with_paths = set()
    path_count = 1
    coords = canvas.cache['coords']

    for room_name, doors in total_door_coords.items():
        for door in doors:
            # detect the nearest door, using distance()
            matches = canvas.match(
                                   tile_type='door',
                                   ignore=(room_name,)
                                  )
            door_distances = {
                              door_coord: distance(door, door_coord)
                              for door_coord in matches
                              if not door_coord in doors_with_paths
                             }

            if door_distances:
                # we could cycle through doors until it doesn't overlap with
                # path.
                closest_door = min(door_distances, key=door_distances.get)
                path = astar(canvas, door, closest_door)
                if path is None: continue

                # check if path in any rooms, if it is, then remove
                subset_coords = canvas.get_subset_coords(get_all=True, ignore=('river', 'lake'))
                remove = path.intersection(subset_coords)
                path = path.difference(remove)

                if path:
                    # if intersections with river, then let's make a bridge!
                    water_coords = canvas.match(tile_type='water')
                    water_coords.extend(canvas.match(tile_type='bridge'))
                    bridges = path.intersection(frozenset(water_coords))

                    # this will remove it from the path subset?
                    if bridges:
                        canvas.update(bridges, tile_type='bridge')

                    doors_with_paths.add(door)

                    # now before we draw the path, remove the bridges
                    # from the path!
                    path = path.difference(bridges)
                    canvas.subset(
                                  'path_%s' % path_count,
                                  path,
                                  tile_type='path'
                                 )
                    path_count += 1

    # remove redundant doors that go nowhere...
    replace_these_doors = set()

    for doors in total_door_coords.values():
        for door in doors:
            neighbors = sqlcanvas.adjacent(
                                           door,
                                           viable_plots=coords
                                          )['adjacent']
            has_path = False

            # any of our neighbors a path?
            for neighbor in neighbors:
                if canvas[neighbor]['tile_type'] == 'path':
                    has_path = True
                    break

            # this door has a path; leave it be!
            if has_path:
                continue
            else:  # no path for this door; mark to be replaced...
                replace_these_doors.add(door)

    canvas.update(replace_these_doors, tile_type='wall')
    return path_count


# doors -----------------------------------------------------------------------


def room_place_doors(canvas, room_area, room_max_doors=4):
    room_boundaries = brush.parameter(room_area)
    canvas_boundaries = canvas.get_parameter()

    # walls, doors
    possible_doors = len(room_boundaries) - 4  # - corners
    possible_doors = min([possible_doors, room_max_doors])
    possible_doors = random.randint(1, possible_doors)

    # we have to assure doors don't end up on boundaries
    while True:
        walls, doors = brush.omit_random(
                                         room_boundaries,
                                         possible_doors,
                                         not_corners=True
                                        )

        if doors and not canvas_boundaries & doors:
            break

    canvas.update(doors, tile_type='door')
    return doors


def room_link_doors():
    pass


# A* ALGORITHM/PATH GENERATION ################################################


def distance(plot_a, plot_b):
    """The Distance formula."""

    a_x, a_y = plot_a
    b_x, b_y = plot_b
    x = a_x - b_x
    y = a_y - b_y
    return math.sqrt(x * x + y * y)


def heuristic_cost_estimate(start, goal):
    diff_x = math.fabs(start[0] - goal[0])
    diff_y = math.fabs(start[1] - goal[1])
    return 10 * (diff_x + diff_y)


def reconstruct_path(came_from, current_node):
    if current_node in came_from:
        p = reconstruct_path(came_from, came_from[current_node])
        return p + (current_node,)  # p + current_node
    else:
        return (current_node,)


def astar(canvas, start, goal, strict=False):
    coordinates = canvas.cache['coords']
    closedset = set()  # set of nodes already evaluated
    openset = set([start])  # set of tentative nodes to be evaluated
    came_from = {}  # map of navigated nodes
    g_score = {start: 0}  # cost from start along best known path

    # estimated total cost from start to goal through y
    f_score = {start: heuristic_cost_estimate(start, goal)}

    while openset:
        # the node in openset having the lowest f_score[] value.
        openset_f_scores = {}

        for plot in openset:
            score = f_score.get(plot, None)

            if score is None:
                continue

            openset_f_scores[plot] = score

        current = min(openset_f_scores, key=openset_f_scores.get)

        if current == goal:
            return set(reconstruct_path(came_from, goal))

        openset.remove(current)
        closedset.add(current)

        for neighbor in sqlcanvas.adjacent(current, coordinates)['adjacent']:
            tentative_g_score = g_score[current] + distance(current, neighbor)

            # needs to reference tile_type's impassable value
            tile_type = canvas[neighbor]['tile_type']
            tile_data = TILE_TYPES[tile_type]
           
            if tile_type == 'water':
                tentative_g_score += 8

            # i allow rivers to be passed for paths, but what about houses
            # being placed over rivers?!
            if tile_type != 'water' and tile_data['impassable'] == 'true':
                closedset.add(neighbor)
                continue

            if (neighbor in closedset
                and tentative_g_score >= g_score[neighbor]):
                
                continue

            if (neighbor not in openset
                or tentative_g_score < g_score[neighbor]):

                came_from[neighbor] = current
                g_score[neighbor] = tentative_g_score
                f_score[neighbor] = (tentative_g_score
                                     + heuristic_cost_estimate(neighbor, goal))

                if neighbor not in openset:
                    openset.add(neighbor)

    if strict:
        raise Exception('AStar: Impossible!')
    else:
        return None
