FROM ros:iron-ros-base

# Install ROS 2 web_video_server
RUN apt-get update && \
    apt-get install -y --no-install-recommends ros-iron-web-video-server && \
    rm -rf /var/lib/apt/lists/*

# Start the server on 0.0.0.0:8080
CMD bash -lc "source /opt/ros/iron/setup.bash && \
              ros2 run web_video_server web_video_server \
              --port 8080 --address 0.0.0.0"
